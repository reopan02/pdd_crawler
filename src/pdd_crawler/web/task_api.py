"""Crawl task management API endpoints.

Uses chrome_pool to connect to shop Chrome containers via CDP.
"""

from __future__ import annotations

import asyncio
import json
import tempfile
import shutil
from pathlib import Path

from fastapi import APIRouter, Request, HTTPException
from sse_starlette.sse import EventSourceResponse

from pdd_crawler import config
from pdd_crawler.web.deps import get_session_id, chrome_pool
from pdd_crawler.web.session_store import store

router = APIRouter(tags=["tasks"])


@router.post("/crawl/start")
async def start_crawl(request: Request):
    """Start a crawl task for one or more shops.

    Body: {"shop_ids": ["shop1", ...], "operations": ["scrape_home", "export_bills"]}
    """
    session_id = get_session_id(request)
    body = await request.json()

    shop_ids = body.get("shop_ids", [])
    if "shop_id" in body and not shop_ids:
        shop_ids = [body["shop_id"]]

    # Backward compat: accept cookie_ids as shop_ids
    if not shop_ids and "cookie_ids" in body:
        shop_ids = body["cookie_ids"]
    if not shop_ids and "cookie_id" in body:
        shop_ids = [body["cookie_id"]]

    operations = body.get("operations", ["scrape_home", "export_bills"])

    if not shop_ids:
        raise HTTPException(status_code=422, detail="缺少 shop_ids")

    for sid in shop_ids:
        if config.get_endpoint(sid) is None:
            raise HTTPException(status_code=404, detail=f"店铺不存在: {sid}")

    task_type = "full" if len(operations) > 1 else operations[0]
    task = store.create_task(session_id, task_type)

    asyncio.create_task(
        _crawl_background(session_id, task.task_id, shop_ids, operations)
    )

    return {"task_id": task.task_id, "status": "pending"}


@router.get("/tasks")
async def list_tasks(request: Request):
    """List all tasks in the current session."""
    session_id = get_session_id(request)
    tasks = store.list_tasks(session_id)
    return {
        "tasks": [
            {
                "task_id": t.task_id,
                "task_type": t.task_type,
                "status": t.status,
                "progress": t.progress,
                "message": t.message,
                "error": t.error,
                "has_data": bool(t.data),
                "file_count": len(t.files),
            }
            for t in tasks
        ]
    }


@router.get("/tasks/{task_id}")
async def get_task(request: Request, task_id: str):
    """Get task status and result."""
    session_id = get_session_id(request)
    task = store.get_task(session_id, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")

    result = {
        "task_id": task.task_id,
        "task_type": task.task_type,
        "status": task.status,
        "progress": task.progress,
        "message": task.message,
        "error": task.error,
        "file_count": len(task.files),
    }

    if task.status == "completed" and task.data:
        safe_data = {k: v for k, v in task.data.items() if k not in ("qr_image",)}
        result["data"] = safe_data

    return result


@router.get("/tasks/{task_id}/progress")
async def task_progress_stream(request: Request, task_id: str):
    """SSE stream for task progress updates."""
    session_id = get_session_id(request)

    async def event_generator():
        task = store.get_task(session_id, task_id)
        if task is None:
            yield {"event": "error", "data": json.dumps({"error": "任务不存在"})}
            return

        last_progress = -1
        last_message = ""
        log_cursor = 0

        while task.status in ("pending", "running"):
            if task.progress != last_progress or task.message != last_message:
                yield {
                    "event": "progress",
                    "data": json.dumps(
                        {
                            "status": task.status,
                            "progress": task.progress,
                            "message": task.message,
                        }
                    ),
                }
                last_progress = task.progress
                last_message = task.message

            log_entries, log_cursor = task.log.read_since(log_cursor)
            for entry in log_entries:
                yield {
                    "event": "log",
                    "data": json.dumps({"msg": entry.msg, "ts": entry.ts}),
                }

            await asyncio.sleep(1)

        # Flush remaining logs
        log_entries, log_cursor = task.log.read_since(log_cursor)
        for entry in log_entries:
            yield {
                "event": "log",
                "data": json.dumps({"msg": entry.msg, "ts": entry.ts}),
            }

        if task.status == "completed":
            yield {
                "event": "completed",
                "data": json.dumps(
                    {
                        "status": "completed",
                        "message": task.message,
                        "file_count": len(task.files),
                        "has_data": bool(task.data),
                    }
                ),
            }
        else:
            yield {
                "event": "error",
                "data": json.dumps(
                    {"status": "failed", "error": task.error or "任务失败"}
                ),
            }

    return EventSourceResponse(event_generator())


@router.get("/tasks/{task_id}/download/{file_index}")
async def download_task_file(request: Request, task_id: str, file_index: int):
    """Raw crawl data download is disabled."""
    session_id = get_session_id(request)
    task = store.get_task(session_id, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task.status != "completed":
        raise HTTPException(status_code=400, detail="任务未完成")
    raise HTTPException(
        status_code=403,
        detail="未清洗数据不支持下载，请先在数据清洗与处理中生成并下载清洗结果",
    )


@router.get("/tasks/{task_id}/result")
async def get_task_result(request: Request, task_id: str):
    """Get the data result of a completed task (JSON)."""
    session_id = get_session_id(request)
    task = store.get_task(session_id, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task.status != "completed":
        raise HTTPException(status_code=400, detail="任务未完成")

    return {
        "task_id": task.task_id,
        "data": task.data,
        "files": [
            {"index": i, "filename": f["filename"], "size": len(f["content"])}
            for i, f in enumerate(task.files)
        ],
    }


# ── Background crawl implementation ──────────────────────


async def _crawl_background(
    session_id: str,
    task_id: str,
    shop_ids: list[str],
    operations: list[str],
) -> None:
    """Background task: run crawl operations via CDP."""
    task = store.get_task(session_id, task_id)
    if task is None:
        return

    task.status = "running"
    task.message = "正在准备..."
    task.log.append("采集任务启动")

    try:
        total_shops = len(shop_ids)
        for s_idx, shop_id in enumerate(shop_ids):
            ep = config.get_endpoint(shop_id)
            if ep is None:
                continue

            shop_name = ep.shop_name
            task.message = f"正在处理 {shop_name} ({s_idx + 1}/{total_shops})..."
            task.log.append(f"[{s_idx + 1}/{total_shops}] 开始处理: {shop_name}")

            tmp_download_dir = Path(tempfile.mkdtemp(prefix="pdd_bills_"))

            try:
                async with chrome_pool.acquire(shop_id) as page:
                    total_ops = len(operations)
                    current_op = 0
                    base_progress = int(s_idx / total_shops * 100)
                    progress_weight = 100 / total_shops

                    # ── Scrape home ──
                    if "scrape_home" in operations:
                        current_op += 1
                        op_progress = int(
                            (current_op - 1) / total_ops * progress_weight
                        )
                        task.message = f"[{shop_name}] 正在抓取首页数据..."
                        task.log.append("  → 抓取首页概览数据...")
                        task.progress = base_progress + op_progress + 5

                        try:
                            from pdd_crawler.home_scraper import scrape_home

                            home_data = await scrape_home(page)
                            if "home_data" not in task.data:
                                task.data["home_data"] = []
                            task.data["home_data"].append(
                                {
                                    "shop_id": shop_id,
                                    "shop_name": shop_name,
                                    "data": home_data,
                                }
                            )
                            # Update shop name from actual page
                            actual_name = str(home_data.get("shop_name", ""))
                            if actual_name:
                                shop_name = actual_name
                                ep.shop_name = actual_name

                            task.log.append("  → 首页数据抓取完成 ✓")
                            task.progress = base_progress + int(
                                current_op / total_ops * progress_weight
                            )
                        except RuntimeError as e:
                            if "会话已过期" in str(e):
                                task.log.append("  → 会话已过期，需要重新登录")
                            raise

                    # ── Export bills ──
                    if "export_bills" in operations:
                        current_op += 1
                        op_progress = int(
                            (current_op - 1) / total_ops * progress_weight
                        )
                        task.message = f"[{shop_name}] 正在导出账单..."
                        task.log.append("  → 导出账单 (SSO → cashier → 下载CSV)...")
                        task.progress = base_progress + op_progress + 5

                        from pdd_crawler.bill_exporter import export_all_bills

                        downloaded_paths = await export_all_bills(
                            page, tmp_download_dir
                        )

                        for fpath in downloaded_paths:
                            if fpath.exists():
                                content = fpath.read_bytes()
                                media_type = (
                                    "text/csv"
                                    if fpath.suffix.lower() == ".csv"
                                    else "application/octet-stream"
                                )
                                task.files.append(
                                    {
                                        "filename": f"{shop_name}_{fpath.name}",
                                        "content": content,
                                        "media_type": media_type,
                                    }
                                )

                        task.progress = base_progress + int(
                            current_op / total_ops * progress_weight
                        )
                        task.log.append(
                            f"  → 账单导出完成, {len(downloaded_paths)} 个文件 ✓"
                        )

            finally:
                if tmp_download_dir.exists():
                    shutil.rmtree(tmp_download_dir, ignore_errors=True)

        task.status = "completed"
        task.progress = 100
        task.message = "全部完成"
        task.log.append("采集任务全部完成 ✓")
        task.log.finished = True

    except Exception as e:
        task.status = "failed"
        task.error = str(e)
        task.message = f"任务失败: {e}"
        task.log.append(f"任务失败: {e}")
        task.log.finished = True
