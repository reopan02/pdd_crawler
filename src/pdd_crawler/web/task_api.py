"""Crawl task management API endpoints."""

from __future__ import annotations

import asyncio
import json
import tempfile

from pathlib import Path

from fastapi import APIRouter, Request, HTTPException
from sse_starlette.sse import EventSourceResponse

from pdd_crawler.web.deps import get_session_id, browser_semaphore
from pdd_crawler.web.session_store import store

router = APIRouter(tags=["tasks"])


@router.post("/crawl/start")
async def start_crawl(request: Request):
    """Start a crawl task for multiple cookies.

    Body: {"cookie_ids": ["..."], "operations": ["scrape_home", "export_bills"]}
    """
    session_id = get_session_id(request)
    body = await request.json()

    cookie_ids = body.get("cookie_ids", [])
    if "cookie_id" in body and not cookie_ids:
        cookie_ids = [body["cookie_id"]]

    operations = body.get("operations", ["scrape_home", "export_bills"])

    if not cookie_ids:
        raise HTTPException(status_code=422, detail="缺少 cookie_ids")

    for cid in cookie_ids:
        if store.get_cookie(session_id, cid) is None:
            raise HTTPException(status_code=404, detail=f"Cookie {cid} 不存在")

    task_type = "full" if len(operations) > 1 else operations[0]
    task = store.create_task(session_id, task_type)

    # Launch crawl in background
    asyncio.create_task(
        _crawl_background(session_id, task.task_id, cookie_ids, operations)
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

    # Include data if completed (exclude large binary fields)
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
            await asyncio.sleep(1)

        # Final event
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
                    {
                        "status": "failed",
                        "error": task.error or "任务失败",
                    }
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
        detail="未清洗数据不支持下载，请先在“数据清洗与处理”中生成并下载清洗结果",
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
    cookie_ids: list[str],
    operations: list[str],
) -> None:
    """Background task: run crawl operations."""
    task = store.get_task(session_id, task_id)
    if task is None:
        return

    task.status = "running"
    task.message = "正在准备..."

    try:
        total_cookies = len(cookie_ids)
        for c_idx, cookie_id in enumerate(cookie_ids):
            entry = store.get_cookie(session_id, cookie_id)
            if entry is None:
                continue

            task.message = (
                f"正在处理 {entry.shop_name} ({c_idx + 1}/{total_cookies})..."
            )

            tmp_path = None
            try:
                async with browser_semaphore:
                    # Write storage_state to temp file
                    tmp = tempfile.NamedTemporaryFile(
                        suffix=".json", delete=False, mode="w", encoding="utf-8"
                    )
                    json.dump(entry.storage_state, tmp)
                    tmp.close()
                    tmp_path = Path(tmp.name)

                    # Create temp dir for downloads
                    tmp_download_dir = Path(tempfile.mkdtemp(prefix="pdd_bills_"))

                    from pdd_crawler.cookie_manager import create_crawler
                    from pdd_crawler.home_scraper import scrape_home
                    from pdd_crawler.crawl4ai_bill_exporter import export_all_bills

                    import uuid

                    crawl_session_id = str(uuid.uuid4())

                    crawler = await create_crawler(
                        cookie_path=tmp_path,
                        headless=True,
                        downloads_path=tmp_download_dir,
                    )

                    try:
                        total_ops = len(operations)
                        current_op = 0
                        base_cookie_progress = int(c_idx / total_cookies * 100)
                        cookie_progress_weight = 100 / total_cookies

                        # ── Scrape home ──
                        if "scrape_home" in operations:
                            current_op += 1
                            op_progress = int(
                                (current_op - 1) / total_ops * cookie_progress_weight
                            )
                            task.message = f"[{entry.shop_name}] 正在抓取首页数据..."
                            task.progress = base_cookie_progress + op_progress + 5

                            try:
                                home_data = await scrape_home(crawler, crawl_session_id)
                                if "home_data" not in task.data:
                                    task.data["home_data"] = []
                                task.data["home_data"].append(
                                    {
                                        "cookie_id": cookie_id,
                                        "shop_name": entry.shop_name,
                                        "data": home_data,
                                    }
                                )
                                task.progress = base_cookie_progress + int(
                                    current_op / total_ops * cookie_progress_weight
                                )
                            except RuntimeError as e:
                                if "会话已过期" in str(e):
                                    entry.status = "invalid"
                                raise

                        # ── Export bills ──
                        if "export_bills" in operations:
                            current_op += 1
                            op_progress = int(
                                (current_op - 1) / total_ops * cookie_progress_weight
                            )
                            task.message = f"[{entry.shop_name}] 正在导出账单..."
                            task.progress = base_cookie_progress + op_progress + 5

                            downloaded_paths = await export_all_bills(
                                crawler,
                                crawl_session_id,
                                tmp_path,
                                tmp_download_dir,
                            )

                            # Read downloaded files into memory
                            for fpath in downloaded_paths:
                                if fpath.exists():
                                    content = fpath.read_bytes()
                                    media_type = (
                                        "text/csv"
                                        if fpath.suffix.lower() == ".csv"
                                        else "application/octet-stream"
                                    )
                                    # prepend shop name to filename to avoid conflicts
                                    task.files.append(
                                        {
                                            "filename": f"{entry.shop_name}_{fpath.name}",
                                            "content": content,
                                            "media_type": media_type,
                                        }
                                    )

                            task.progress = base_cookie_progress + int(
                                current_op / total_ops * cookie_progress_weight
                            )

                    finally:
                        await crawler.close()

                        # Clean up temp download dir
                        import shutil

                        if tmp_download_dir.exists():
                            shutil.rmtree(tmp_download_dir, ignore_errors=True)

            finally:
                if tmp_path and tmp_path.exists():
                    tmp_path.unlink(missing_ok=True)

        task.status = "completed"
        task.progress = 100
        task.message = "全部完成"

    except Exception as e:
        task.status = "failed"
        task.error = str(e)
        task.message = f"任务失败: {e}"
