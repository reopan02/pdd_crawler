"""Shop manager — validates login state via CDP connections.

Replaces the old cookie_manager.py. No crawl4ai dependency.
"""

from __future__ import annotations

import asyncio
from typing import Callable

from pdd_crawler import config
from pdd_crawler.chrome_pool import ChromePool


async def validate_shop(
    pool: ChromePool,
    shop_id: str,
    log_callback: Callable[[str], None] | None = None,
) -> bool:
    """Validate a shop's Chrome container has valid MMS + cashier SSO session.

    Steps:
      1. Navigate to MMS homepage — check not redirected to /login.
      2. Navigate to MMS cashier proxy URL — triggers SSO ticket generation.
      3. Verify redirect lands on cashier.pinduoduo.com (ticket accepted).
    """

    def _log(msg: str) -> None:
        print(msg)
        if log_callback:
            log_callback(msg)

    ep = config.get_endpoint(shop_id)
    if ep is None:
        _log(f"[Shop] 未找到店铺配置: {shop_id}")
        return False

    try:
        async with pool.acquire(shop_id) as page:
            # ── Step 1: MMS login check ──
            _log("  → Step 1/2: 访问 MMS 首页，检查登录态...")
            await page.goto(
                "https://mms.pinduoduo.com",
                wait_until="domcontentloaded",
                timeout=config.PAGE_LOAD_TIMEOUT,
            )
            await asyncio.sleep(2)

            current_url = page.url or ""
            if "/login" in current_url:
                _log("  → Step 1/2: 未登录，MMS 重定向到登录页")
                return False
            _log("  → Step 1/2: MMS 登录态有效 ✓")

            # ── Step 2: Cashier SSO ticket flow ──
            _log("  → Step 2/2: 发起 SSO 认证 (getJumpUrl → cashier ticket)...")
            try:
                await page.goto(
                    config.MMS_CASHIER_PROXY_URL,
                    wait_until="domcontentloaded",
                    timeout=30000,
                )
            except Exception as e:
                _log(f"  → SSO 代理页访问超时: {e}")

            await asyncio.sleep(3)
            try:
                await page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass

            sso_url = page.url or ""
            if "cashier.pinduoduo.com" in sso_url:
                body_text = await page.evaluate("document.body.innerText || ''") or ""
                blocked_texts = ["登录异常", "关闭页面后重试"]
                if any(t in body_text for t in blocked_texts):
                    _log(f"  → SSO 到达 cashier 但被风控拦截: {sso_url}")
                    return False
                _log("  → Step 2/2: SSO 验证通过, cashier 会话已建立 ✓")
                return True
            else:
                _log(f"  → SSO 重定向未到达 cashier: {sso_url}")
                return False
    except Exception as e:
        _log(f"  → 验证异常: {e}")
        return False
