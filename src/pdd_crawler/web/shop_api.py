"""Shop management API endpoints.

Replaces cookie_api.py. Manages Chrome containers via CDP:
- List shops (from static config + live connection status)
- QR login via CDP screenshot push (SSE)
- Validate login state
- VNC URL for manual fallback
"""

from __future__ import annotations

import asyncio
import base64
import json

from fastapi import APIRouter, Request, HTTPException
from sse_starlette.sse import EventSourceResponse

from pdd_crawler import config
from pdd_crawler.web.deps import get_session_id, chrome_pool
from pdd_crawler.web.session_store import store
from pdd_crawler.web.data_store import save_shop, delete_shop

router = APIRouter(tags=["shops"])


# ── List shops ────────────────────────────────────────────


@router.get("/shops")
async def list_shops(request: Request):
    """List all configured shops with connection and login status."""
    shops = chrome_pool.list_shops()
    return {"shops": shops}


@router.get("/shops/{shop_id}")
async def get_shop(request: Request, shop_id: str):
    """Get a single shop's status."""
    ep = config.get_endpoint(shop_id)
    if ep is None:
        raise HTTPException(status_code=404, detail=f"店铺不存在: {shop_id}")

    connected = chrome_pool.is_connected(shop_id)
    logged_in = chrome_pool.get_login_status(shop_id)

    return {
        "shop_id": ep.shop_id,
        "shop_name": ep.shop_name,
        "cdp_url": ep.cdp_url,
        "vnc_url": ep.vnc_url,
        "connected": connected,
        "logged_in": logged_in,
    }


# ── Add / Remove shops ──────────────────────────────────


@router.post("/shops")
async def add_shop(request: Request):
    """Add a new shop dynamically.

    Body: {"shop_id": "shop2", "shop_name": "店铺2",
           "cdp_url": "http://...:9223", "vnc_url": "http://...:6081"}
    """
    body = await request.json()
    shop_id = body.get("shop_id", "").strip()
    shop_name = body.get("shop_name", "").strip()
    cdp_url = body.get("cdp_url", "").strip()
    vnc_url = body.get("vnc_url", "").strip()

    if not shop_id or not shop_name or not cdp_url:
        raise HTTPException(
            status_code=422, detail="shop_id, shop_name, cdp_url 为必填项"
        )

    # Persist to SQLite + register in config
    save_shop(shop_id, shop_name, cdp_url, vnc_url)

    # Register lock in ChromePool so it can be acquired
    chrome_pool.register_shop(shop_id)

    return {"status": "ok", "shop_id": shop_id, "message": f"店铺 {shop_name} 已添加"}


@router.delete("/shops/{shop_id}")
async def remove_shop(request: Request, shop_id: str):
    """Remove a shop."""
    ep = config.get_endpoint(shop_id)
    if ep is None:
        raise HTTPException(status_code=404, detail=f"店铺不存在: {shop_id}")

    # Disconnect from ChromePool first
    await chrome_pool.unregister_shop(shop_id)

    # Remove from SQLite + config
    delete_shop(shop_id)

    return {"status": "ok", "shop_id": shop_id, "message": "店铺已删除"}


# ── Validate login ───────────────────────────────────────


@router.post("/shops/{shop_id}/validate")
async def validate_shop(request: Request, shop_id: str):
    """Validate a shop's login state (MMS + cashier SSO)."""
    ep = config.get_endpoint(shop_id)
    if ep is None:
        raise HTTPException(status_code=404, detail=f"店铺不存在: {shop_id}")

    try:
        from pdd_crawler.shop_manager import validate_shop as _validate

        is_valid = await _validate(chrome_pool, shop_id)
        return {
            "shop_id": shop_id,
            "valid": is_valid,
            "status": "valid" if is_valid else "invalid",
        }
    except Exception as e:
        return {
            "shop_id": shop_id,
            "valid": False,
            "status": "error",
            "error": str(e),
        }


@router.post("/shops/validate-all")
async def validate_all_shops(request: Request):
    """Validate all shops. Returns results for each."""
    session_id = get_session_id(request)
    log = store.get_or_create_log(session_id, "validate-all")
    log._lines.clear()
    log.finished = False

    endpoints = config.CHROME_ENDPOINTS
    log.append(f"开始验证 {len(endpoints)} 个店铺...")

    asyncio.create_task(_validate_all_background(session_id, log))

    return {
        "status": "ok",
        "message": f"已启动 {len(endpoints)} 个店铺的验证",
        "count": len(endpoints),
    }


@router.get("/shops/validate-all/stream")
async def validate_all_stream(request: Request):
    """SSE stream for validation progress."""
    session_id = get_session_id(request)

    async def event_generator():
        log = store.get_log(session_id, "validate-all")
        if log is None:
            yield {
                "event": "error",
                "data": json.dumps({"error": "没有正在进行的验证"}),
            }
            return

        cursor = 0
        while not log.finished:
            entries, cursor = log.read_since(cursor)
            for entry in entries:
                yield {
                    "event": "log",
                    "data": json.dumps({"msg": entry.msg, "ts": entry.ts}),
                }
            await asyncio.sleep(1)

        entries, cursor = log.read_since(cursor)
        for entry in entries:
            yield {
                "event": "log",
                "data": json.dumps({"msg": entry.msg, "ts": entry.ts}),
            }
        yield {"event": "done", "data": json.dumps({"msg": "验证完成"})}

    return EventSourceResponse(event_generator())


async def _validate_all_background(session_id: str, log) -> None:
    """Validate all shops sequentially."""
    from pdd_crawler.shop_manager import validate_shop as _validate

    endpoints = config.CHROME_ENDPOINTS
    valid_count = 0
    invalid_count = 0

    for i, ep in enumerate(endpoints):
        log.append(f"[{i + 1}/{len(endpoints)}] 验证: {ep.shop_name}")
        try:
            is_valid = await _validate(chrome_pool, ep.shop_id, log_callback=log.append)
            if is_valid:
                valid_count += 1
                log.append(f"  → {ep.shop_name}: ✓ 有效")
            else:
                invalid_count += 1
                log.append(f"  → {ep.shop_name}: ✗ 失效")
        except Exception as e:
            invalid_count += 1
            log.append(f"  → {ep.shop_name}: ✗ 异常: {e}")

    log.append(f"全部验证完成: {valid_count} 有效, {invalid_count} 失效")
    log.finished = True


# ── QR Login via CDP + SSE ────────────────────────────────


@router.post("/shops/{shop_id}/login")
async def start_login(request: Request, shop_id: str):
    """Start QR login for a shop. Returns task_id for SSE streaming."""
    ep = config.get_endpoint(shop_id)
    if ep is None:
        raise HTTPException(status_code=404, detail=f"店铺不存在: {shop_id}")

    session_id = get_session_id(request)
    task = store.create_task(session_id, "qr_login")
    task.data["shop_id"] = shop_id

    asyncio.create_task(_qr_login_background(session_id, task.task_id, shop_id))

    return {"task_id": task.task_id, "shop_id": shop_id}


@router.get("/shops/{shop_id}/login/{task_id}/stream")
async def login_stream(request: Request, shop_id: str, task_id: str):
    """SSE stream for QR login — pushes QR screenshots and status."""
    session_id = get_session_id(request)

    async def event_generator():
        task = store.get_task(session_id, task_id)
        if task is None:
            yield {"event": "error", "data": json.dumps({"error": "任务不存在"})}
            return

        while task.status in ("pending", "running"):
            qr_image = task.data.get("qr_image")
            if qr_image:
                yield {
                    "event": "qr_code",
                    "data": json.dumps({"image": qr_image, "message": task.message}),
                }
                task.data.pop("qr_image", None)

            if task.status in ("completed", "failed"):
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

        if task.status == "completed":
            yield {
                "event": "completed",
                "data": json.dumps(
                    {
                        "status": "completed",
                        "shop_id": shop_id,
                        "shop_name": task.data.get("shop_name"),
                    }
                ),
            }
        else:
            yield {
                "event": "error",
                "data": json.dumps(
                    {"status": "failed", "error": task.error or "登录失败"}
                ),
            }

    return EventSourceResponse(event_generator())


async def _qr_login_background(session_id: str, task_id: str, shop_id: str) -> None:
    """Background: open MMS login via CDP, screenshot QR, poll for login success."""
    task = store.get_task(session_id, task_id)
    if task is None:
        return

    task.status = "running"
    task.message = "正在连接浏览器..."

    try:
        async with chrome_pool.acquire(shop_id) as page:
            task.message = "正在打开登录页面..."
            await page.goto(
                "https://mms.pinduoduo.com",
                wait_until="domcontentloaded",
                timeout=config.PAGE_LOAD_TIMEOUT,
            )
            await asyncio.sleep(2)

            task.message = "请使用拼多多 APP 扫描二维码"

            elapsed = 0
            timeout = config.QR_LOGIN_TIMEOUT
            poll_interval = config.LOGIN_POLL_INTERVAL

            while elapsed < timeout:
                # Screenshot QR code canvas
                try:
                    qr_canvas = page.locator("canvas").first
                    if await page.locator("canvas").count() > 0:
                        screenshot_bytes = await qr_canvas.screenshot(type="png")
                    else:
                        screenshot_bytes = await page.screenshot(type="png")
                    qr_b64 = base64.b64encode(screenshot_bytes).decode("ascii")
                    task.data["qr_image"] = qr_b64
                except Exception:
                    pass

                # Check if login succeeded
                current_url = page.url or ""
                if "/login" not in current_url and "mms.pinduoduo.com" in current_url:
                    task.message = "登录成功！"
                    task.progress = 80

                    # Extract shop name
                    from pdd_crawler.home_scraper import get_shop_name

                    shop_name = await get_shop_name(page)

                    # Update config endpoint name if detected
                    ep = config.get_endpoint(shop_id)
                    if ep and shop_name:
                        ep.shop_name = shop_name

                    task.status = "completed"
                    task.progress = 100
                    task.message = f"登录成功: {shop_name}"
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

    except Exception as e:
        task.status = "failed"
        task.error = str(e)
        task.message = f"登录失败: {e}"
