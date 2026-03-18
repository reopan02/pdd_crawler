"""Cookie management API endpoints."""

from __future__ import annotations

import asyncio
import base64
import io
import json
import tempfile
import uuid
import zipfile
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Request, UploadFile, File, HTTPException
from fastapi.responses import Response
from sse_starlette.sse import EventSourceResponse

from pdd_crawler.web.deps import get_session_id, browser_semaphore
from pdd_crawler.web.session_store import store, CookieEntry

router = APIRouter(tags=["cookies"])


def _validate_storage_state(data: dict) -> tuple[bool, str]:
    """Validate that data looks like a Playwright storage_state JSON."""
    if not isinstance(data, dict):
        return False, "JSON 根节点必须是对象"
    if "cookies" not in data:
        return False, "缺少 'cookies' 字段"
    if not isinstance(data["cookies"], list):
        return False, "'cookies' 必须是数组"
    for i, c in enumerate(data["cookies"]):
        if not isinstance(c, dict):
            return False, f"cookies[{i}] 必须是对象"
        for required in ("name", "value", "domain"):
            if required not in c:
                return False, f"cookies[{i}] 缺少 '{required}' 字段"
    return True, ""


def _extract_shop_name_from_cookies(data: dict) -> str:
    """Try to extract shop name from cookie values or return a default."""
    cookies = data.get("cookies", [])
    # Look for common PDD shop name indicators in cookie values
    for c in cookies:
        name = c.get("name", "")
        if "mall" in name.lower() or "shop" in name.lower():
            val = c.get("value", "")
            if val and len(val) < 100:
                return val
    return f"shop_{str(uuid.uuid4())[:6]}"


@router.post("/cookies/upload")
async def upload_cookie(
    request: Request, files: list[UploadFile] = File(...),
):
    """Upload one or more Playwright storage_state JSON files."""
    session_id = get_session_id(request)
    results = []

    for file in files:
        content = await file.read()
        try:
            data = json.loads(content.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            results.append({"filename": file.filename, "error": f"无效的 JSON: {e}"})
            continue

        valid, msg = _validate_storage_state(data)
        if not valid:
            results.append({"filename": file.filename, "error": f"格式错误: {msg}"})
            continue

        # Use the original filename as shop name (strip common suffixes)
        raw_name = file.filename or ""
        shop_name = raw_name
        for suffix in ("_cookies.json", ".json"):
            if shop_name.lower().endswith(suffix):
                shop_name = shop_name[: -len(suffix)]
                break
        shop_name = shop_name.strip()
        if not shop_name:
            shop_name = _extract_shop_name_from_cookies(data)
        entry = store.add_cookie(session_id, shop_name, data)

        results.append({
            "filename": file.filename,
            "cookie_id": entry.cookie_id,
            "shop_name": entry.shop_name,
            "cookie_count": len(data.get("cookies", [])),
        })

    return {"status": "ok", "results": results}


@router.get("/cookies")
async def list_cookies(request: Request):
    """List all cookies in the current session."""
    session_id = get_session_id(request)
    entries = store.list_cookies(session_id)
    return {
        "cookies": [
            {
                "cookie_id": e.cookie_id,
                "shop_name": e.shop_name,
                "status": e.status,
                "cookie_count": len(e.storage_state.get("cookies", [])),
            }
            for e in entries
        ]
    }


# ── Batch Operations (MUST be before {cookie_id} routes) ──


@router.post("/cookies/batch/validate")
async def batch_validate(request: Request):
    """Start batch validation for multiple cookies. Returns task_id for SSE."""
    session_id = get_session_id(request)
    body = await request.json()
    cookie_ids: list[str] = body.get("cookie_ids", [])
    if not cookie_ids:
        raise HTTPException(status_code=422, detail="cookie_ids 不能为空")

    for cid in cookie_ids:
        if store.get_cookie(session_id, cid) is None:
            raise HTTPException(status_code=404, detail=f"Cookie {cid} 不存在")

    task = store.create_task(session_id, "validate")
    task.data["cookie_ids"] = cookie_ids
    asyncio.create_task(
        _validate_background(session_id, task.task_id, cookie_ids)
    )
    return {"task_id": task.task_id}


@router.post("/cookies/batch/delete")
async def batch_delete(request: Request):
    """Delete multiple cookies at once."""
    session_id = get_session_id(request)
    body = await request.json()
    cookie_ids: list[str] = body.get("cookie_ids", [])
    if not cookie_ids:
        raise HTTPException(status_code=422, detail="cookie_ids 不能为空")

    deleted = []
    not_found = []
    for cid in cookie_ids:
        if store.remove_cookie(session_id, cid):
            deleted.append(cid)
        else:
            not_found.append(cid)

    return {"status": "ok", "deleted": deleted, "not_found": not_found}


@router.post("/cookies/batch/download")
async def batch_download(request: Request):
    """Download multiple cookies as a single ZIP file."""
    session_id = get_session_id(request)
    body = await request.json()
    cookie_ids: list[str] = body.get("cookie_ids", [])
    if not cookie_ids:
        raise HTTPException(status_code=422, detail="cookie_ids 不能为空")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for cid in cookie_ids:
            entry = store.get_cookie(session_id, cid)
            if entry is None:
                continue
            filename = f"{entry.shop_name}_cookies.json"
            content = json.dumps(entry.storage_state, ensure_ascii=False, indent=2)
            zf.writestr(filename, content)

    buf.seek(0)
    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={
            "Content-Disposition": "attachment; filename=cookies_batch.zip"
        },
    )


@router.get("/cookies/validate/{task_id}/stream")
async def validate_stream(request: Request, task_id: str):
    """SSE stream for cookie validation logs."""
    session_id = get_session_id(request)

    async def event_generator():
        task = store.get_task(session_id, task_id)
        if task is None:
            yield {"event": "error", "data": json.dumps({"error": "任务不存在"})}
            return

        last_log_idx = 0
        while task.status in ("pending", "running"):
            logs = task.data.get("logs", [])
            while last_log_idx < len(logs):
                yield {
                    "event": "log",
                    "data": json.dumps(logs[last_log_idx]),
                }
                last_log_idx += 1
            await asyncio.sleep(0.5)

        # Flush remaining logs
        logs = task.data.get("logs", [])
        while last_log_idx < len(logs):
            yield {"event": "log", "data": json.dumps(logs[last_log_idx])}
            last_log_idx += 1

        # Final event
        yield {
            "event": "completed",
            "data": json.dumps({
                "status": task.status,
                "results": task.data.get("results", {}),
            }),
        }

    return EventSourceResponse(event_generator())


# ── Single Cookie Operations ({cookie_id} routes) ────────


@router.post("/cookies/{cookie_id}/validate")
async def validate_cookie(request: Request, cookie_id: str):
    """Start single cookie validation. Returns task_id for SSE log streaming."""
    session_id = get_session_id(request)
    entry = store.get_cookie(session_id, cookie_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Cookie 不存在")

    task = store.create_task(session_id, "validate")
    task.data["cookie_ids"] = [cookie_id]
    asyncio.create_task(
        _validate_background(session_id, task.task_id, [cookie_id])
    )
    return {"task_id": task.task_id}


@router.delete("/cookies/{cookie_id}")
async def delete_cookie(request: Request, cookie_id: str):
    """Delete a cookie from the session."""
    session_id = get_session_id(request)
    removed = store.remove_cookie(session_id, cookie_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Cookie 不存在")
    return {"status": "ok", "cookie_id": cookie_id}


@router.post("/cookies/{cookie_id}/rename")
async def rename_cookie(request: Request, cookie_id: str):
    """Rename a cookie's shop name."""
    session_id = get_session_id(request)
    entry = store.get_cookie(session_id, cookie_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Cookie 不存在")

    body = await request.json()
    new_name = body.get("shop_name", "").strip()
    if not new_name:
        raise HTTPException(status_code=422, detail="店铺名称不能为空")

    entry.shop_name = new_name
    return {"status": "ok", "cookie_id": cookie_id, "shop_name": new_name}


@router.get("/cookies/{cookie_id}/download")
async def download_cookie(request: Request, cookie_id: str):
    """Download a cookie's storage_state as a JSON file."""
    session_id = get_session_id(request)
    entry = store.get_cookie(session_id, cookie_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Cookie 不存在")

    content = json.dumps(entry.storage_state, ensure_ascii=False, indent=2)
    filename = f"{entry.shop_name}_cookies.json"
    encoded_filename = quote(filename)
    return Response(
        content=content.encode("utf-8"),
        media_type="application/json",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"
        },
    )


# ── Background helpers ────────────────────────────────────


async def _validate_background(
    session_id: str, task_id: str, cookie_ids: list[str]
) -> None:
    """Background: validate one or more cookies with log streaming."""
    task = store.get_task(session_id, task_id)
    if task is None:
        return

    task.status = "running"
    task.data.setdefault("logs", [])
    task.data.setdefault("results", {})

    def _add_log(cookie_id: str, level: str, message: str) -> None:
        task.data["logs"].append({
            "cookie_id": cookie_id,
            "level": level,
            "message": message,
        })

    for idx, cookie_id in enumerate(cookie_ids):
        entry = store.get_cookie(session_id, cookie_id)
        if entry is None:
            _add_log(cookie_id, "fail", "Cookie 不存在")
            task.data["results"][cookie_id] = False
            continue

        entry.status = "validating"
        shop = entry.shop_name or cookie_id
        _add_log(cookie_id, "step", f"[{idx+1}/{len(cookie_ids)}] 开始验证: {shop}")

        tmp_path = None
        try:
            async with browser_semaphore:
                tmp = tempfile.NamedTemporaryFile(
                    suffix=".json", delete=False, mode="w", encoding="utf-8"
                )
                json.dump(entry.storage_state, tmp)
                tmp.close()
                tmp_path = Path(tmp.name)

                from pdd_crawler.cookie_manager import validate_cookies

                async def _log_cb(level: str, msg: str) -> None:
                    _add_log(cookie_id, level, msg)

                is_valid, detail = await validate_cookies(tmp_path, log=_log_cb)

            entry.status = "valid" if is_valid else "invalid"
            task.data["results"][cookie_id] = is_valid
        except Exception as e:
            entry.status = "invalid"
            task.data["results"][cookie_id] = False
            _add_log(cookie_id, "fail", f"验证异常: {e}")
        finally:
            if tmp_path and tmp_path.exists():
                tmp_path.unlink(missing_ok=True)

    task.status = "completed"
    task.progress = 100


# ── QR Login via SSE ──────────────────────────────────────


@router.post("/qr-login/start")
async def qr_login_start(request: Request):
    """Start a QR login session. Returns task_id for SSE streaming."""
    session_id = get_session_id(request)
    task = store.create_task(session_id, "qr_login")
    # Launch the QR login flow in background
    asyncio.create_task(_qr_login_background(session_id, task.task_id))
    return {"task_id": task.task_id}


@router.get("/qr-login/{task_id}/stream")
async def qr_login_stream(request: Request, task_id: str):
    """SSE stream for QR login progress — pushes QR screenshots and status."""
    session_id = get_session_id(request)

    async def event_generator():
        task = store.get_task(session_id, task_id)
        if task is None:
            yield {"event": "error", "data": json.dumps({"error": "任务不存在"})}
            return

        while task.status in ("pending", "running"):
            # Check for QR image in task data
            qr_image = task.data.get("qr_image")
            if qr_image:
                yield {
                    "event": "qr_code",
                    "data": json.dumps({"image": qr_image, "message": task.message}),
                }
                task.data.pop("qr_image", None)  # Consume it

            if task.status == "completed":
                break
            if task.status == "failed":
                break

            yield {
                "event": "status",
                "data": json.dumps(
                    {
                        "status": task.status,
                        "message": task.message,
                        "progress": task.progress,
                    }
                ),
            }
            await asyncio.sleep(2)

        # Final event
        if task.status == "completed":
            yield {
                "event": "completed",
                "data": json.dumps(
                    {
                        "status": "completed",
                        "cookie_id": task.data.get("cookie_id"),
                        "shop_name": task.data.get("shop_name"),
                    }
                ),
            }
        else:
            yield {
                "event": "error",
                "data": json.dumps(
                    {
                        "status": "failed",
                        "error": task.error or "登录失败",
                    }
                ),
            }

    return EventSourceResponse(event_generator())


async def _qr_login_background(session_id: str, task_id: str) -> None:
    """Background task: open browser, screenshot QR, wait for login."""
    task = store.get_task(session_id, task_id)
    if task is None:
        return

    task.status = "running"
    task.message = "正在启动浏览器..."

    try:
        async with browser_semaphore:
            from pdd_crawler.cookie_manager import create_crawler
            from pdd_crawler.home_scraper import get_shop_name
            from crawl4ai import CrawlerRunConfig

            crawler = await create_crawler(headless=True)
            crawl_session_id = "qr_login_web"

            try:
                task.message = "正在打开登录页面..."
                await crawler.arun(
                    url="https://mms.pinduoduo.com",
                    config=CrawlerRunConfig(session_id=crawl_session_id),
                )

                # Get the page for screenshots
                page, _ctx = await crawler.crawler_strategy.browser_manager.get_page(  # type: ignore[union-attr]
                    crawlerRunConfig=CrawlerRunConfig(session_id=crawl_session_id),
                )

                task.message = "请使用拼多多 APP 扫描二维码"

                # Poll for QR code and login
                elapsed = 0
                timeout = 120
                poll_interval = 3

                while elapsed < timeout:
                    # Take screenshot of the page (or QR element)
                    try:
                        screenshot_bytes = await page.screenshot(type="png")
                        qr_b64 = base64.b64encode(screenshot_bytes).decode("ascii")
                        task.data["qr_image"] = qr_b64
                    except Exception:
                        pass

                    # Check if login succeeded (URL changed from /login)
                    current_url = page.url or ""
                    if (
                        "/login" not in current_url
                        and "mms.pinduoduo.com" in current_url
                    ):
                        task.message = "登录成功！正在提取信息..."
                        task.progress = 80

                        # Extract shop name
                        shop_name = await get_shop_name(crawler, crawl_session_id)

                        # Extract storage_state
                        _, ctx = await crawler.crawler_strategy.browser_manager.get_page(  # type: ignore[union-attr]
                            crawlerRunConfig=CrawlerRunConfig(
                                session_id=crawl_session_id
                            ),
                        )
                        storage_state = await ctx.storage_state()

                        # Save to session store
                        entry = store.add_cookie(session_id, shop_name, storage_state)

                        task.status = "completed"
                        task.progress = 100
                        task.message = f"登录成功: {shop_name}"
                        task.data["cookie_id"] = entry.cookie_id
                        task.data["shop_name"] = shop_name
                        return

                    await asyncio.sleep(poll_interval)
                    elapsed += poll_interval
                    remaining = timeout - elapsed
                    if remaining > 0:
                        task.message = f"等待扫码... 剩余 {remaining} 秒"
                        task.progress = min(70, int(elapsed / timeout * 70))

                task.status = "failed"
                task.error = f"扫码登录超时（{timeout}秒）"

            finally:
                await crawler.close()

    except Exception as e:
        task.status = "failed"
        task.error = str(e)
        task.message = f"登录失败: {e}"
