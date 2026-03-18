"""Chrome CDP connection pool.

Manages persistent connections to Chrome containers via Chrome DevTools Protocol.
Each shop has a dedicated Chrome instance running in Docker with VNC for manual login.

Usage:
    pool = ChromePool()
    await pool.startup()

    async with pool.acquire("shop1") as page:
        await page.goto("https://mms.pinduoduo.com/home/")
        title = await page.title()

    await pool.shutdown()
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import AsyncIterator
from urllib.parse import urlsplit, urlunsplit

from playwright.async_api import (
    async_playwright,
    Browser,
    BrowserContext,
    Page,
    Playwright,
)

from pdd_crawler import config

# 抑制 Chrome GCM 等无关错误日志
import logging

logging.getLogger("websockets").setLevel(logging.WARNING)
logging.getLogger("playwright").setLevel(logging.WARNING)


@dataclass
class _Connection:
    """A live CDP connection to one Chrome container."""

    shop_id: str
    cdp_url: str
    browser: Browser
    context: BrowserContext
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    logged_in: bool = False


class ChromePool:
    """Manages CDP connections to Chrome containers.

    One connection per shop. Connections are lazy — created on first acquire().
    A per-shop asyncio.Lock ensures only one task uses a container at a time.
    """

    def __init__(self) -> None:
        self._pw: Playwright | None = None
        self._connections: dict[str, _Connection] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    # ── Lifecycle ─────────────────────────────────────────

    async def startup(self) -> None:
        """Initialize Playwright runtime. Call once at app startup."""
        self._pw = await async_playwright().start()
        # Pre-create locks for all configured shops
        for ep in config.CHROME_ENDPOINTS:
            self._locks[ep.shop_id] = asyncio.Lock()
        print(f"[ChromePool] 已启动, {len(config.CHROME_ENDPOINTS)} 个店铺已注册")

    async def shutdown(self) -> None:
        """Disconnect all browsers and stop Playwright."""
        for conn in self._connections.values():
            try:
                await conn.browser.close()
            except Exception:
                pass
        self._connections.clear()
        if self._pw:
            await self._pw.stop()
            self._pw = None
        print("[ChromePool] 已关闭")

    # ── Connection management ─────────────────────────────

    @staticmethod
    def _normalize_cdp_url(cdp_url: str) -> str:
        """Normalize CDP URL to avoid Chrome Host-header restrictions.

        Newer Chrome DevTools endpoints may reject requests whose Host header
        is neither localhost nor an IP literal. When using Docker service names
        (e.g. chrome-shop1), Playwright's initial /json/version probe can fail
        with HTTP 500. Resolve hostname to IP before connecting.
        """
        parts = urlsplit(cdp_url)
        host = parts.hostname
        if not host:
            return cdp_url

        # localhost is always allowed
        if host == "localhost":
            return cdp_url

        # If already an IP literal, keep as-is
        try:
            ipaddress.ip_address(host)
            return cdp_url
        except ValueError:
            pass

        # Resolve service DNS name (e.g. chrome-shop1) to IP
        try:
            resolved_ip = socket.gethostbyname(host)
        except Exception:
            return cdp_url

        # Rebuild netloc preserving optional userinfo and port
        netloc = resolved_ip
        if parts.port is not None:
            netloc = f"{resolved_ip}:{parts.port}"

        return urlunsplit(
            (parts.scheme, netloc, parts.path, parts.query, parts.fragment)
        )

    async def _connect(self, shop_id: str) -> _Connection:
        """Establish a CDP connection to a shop's Chrome container."""
        if self._pw is None:
            raise RuntimeError("ChromePool 未启动, 请先调用 startup()")

        ep = config.get_endpoint(shop_id)
        if ep is None:
            raise ValueError(f"未找到店铺配置: {shop_id}")

        connect_url = self._normalize_cdp_url(ep.cdp_url)

        # Connect via CDP to the running Chrome instance.
        # Chrome may take a few seconds to become ready after container startup,
        # so we retry with exponential backoff to avoid transient ECONNREFUSED.
        last_error: Exception | None = None
        for attempt in range(1, 6):
            try:
                browser = await self._pw.chromium.connect_over_cdp(
                    connect_url,
                    timeout=config.CDP_CONNECT_TIMEOUT,
                )
                break
            except Exception as e:
                last_error = e
                if attempt == 5:
                    raise
                delay = min(8.0, 0.8 * (2 ** (attempt - 1)))
                print(
                    f"[ChromePool] CDP 连接失败({shop_id}) 第{attempt}/5次: {e}; "
                    f"{delay:.1f}s 后重试"
                )
                await asyncio.sleep(delay)
        else:
            # Defensive fallback; practically unreachable due to raise on final attempt.
            raise RuntimeError(f"无法连接到店铺 {shop_id} 的 CDP: {last_error}")

        # Use the first existing context (the one with login state),
        # or create a new one if none exists.
        contexts = browser.contexts
        if contexts:
            context = contexts[0]
        else:
            context = await browser.new_context()

        conn = _Connection(
            shop_id=shop_id,
            cdp_url=ep.cdp_url,
            browser=browser,
            context=context,
        )
        self._connections[shop_id] = conn
        print(f"[ChromePool] 已连接: {shop_id} @ {ep.cdp_url}")
        return conn

    async def _ensure_connection(self, shop_id: str) -> _Connection:
        """Get existing connection or create a new one."""
        conn = self._connections.get(shop_id)
        if conn is not None:
            # Verify connection is still alive
            try:
                _ = conn.browser.contexts
                return conn
            except Exception:
                # Connection dead, remove and reconnect
                print(f"[ChromePool] 连接已断开, 重连: {shop_id}")
                self._connections.pop(shop_id, None)

        return await self._connect(shop_id)

    async def disconnect(self, shop_id: str) -> None:
        """Disconnect a specific shop's browser."""
        conn = self._connections.pop(shop_id, None)
        if conn:
            try:
                await conn.browser.close()
            except Exception:
                pass
            print(f"[ChromePool] 已断开: {shop_id}")

    # ── Page acquisition ──────────────────────────────────

    @asynccontextmanager
    async def acquire(self, shop_id: str) -> AsyncIterator[Page]:
        """Acquire a Page for a shop. Only one caller per shop at a time.

        Usage:
            async with pool.acquire("shop1") as page:
                await page.goto(url)

        The page is NOT closed on exit — it belongs to the persistent
        Chrome container. The lock is released so the next caller can use it.
        """
        lock = self._locks.get(shop_id)
        if lock is None:
            raise ValueError(f"未找到店铺配置: {shop_id}")

        async with lock:
            conn = await self._ensure_connection(shop_id)

            # Get the first open page, or create one
            pages = conn.context.pages
            if pages:
                page = pages[0]
            else:
                page = await conn.context.new_page()

            yield page

    async def get_page(self, shop_id: str) -> Page:
        """Get a page without locking (for read-only checks like login detection).

        Caller is responsible for not conflicting with acquire() usage.
        """
        conn = await self._ensure_connection(shop_id)
        pages = conn.context.pages
        if pages:
            return pages[0]
        return await conn.context.new_page()

    # ── Health & status ───────────────────────────────────

    async def check_login(self, shop_id: str) -> bool:
        """Check if a shop's Chrome is logged into MMS (non-destructive).

        Navigates to MMS home and checks if it redirects to /login.
        """
        try:
            conn = await self._ensure_connection(shop_id)
            pages = conn.context.pages
            page = pages[0] if pages else await conn.context.new_page()

            current_url = page.url or ""
            # If already on MMS home (not login), consider logged in
            if "mms.pinduoduo.com" in current_url and "/login" not in current_url:
                conn.logged_in = True
                return True

            # Navigate to check
            await page.goto(
                config.PDD_HOME_URL,
                wait_until="domcontentloaded",
                timeout=config.PAGE_LOAD_TIMEOUT,
            )
            await asyncio.sleep(2)

            final_url = page.url or ""
            logged_in = "mms.pinduoduo.com" in final_url and "/login" not in final_url
            conn.logged_in = logged_in
            return logged_in
        except Exception as e:
            print(f"[ChromePool] 登录检测失败 {shop_id}: {e}")
            return False

    def is_connected(self, shop_id: str) -> bool:
        """Check if a shop has an active CDP connection."""
        return shop_id in self._connections

    def get_login_status(self, shop_id: str) -> bool:
        """Get cached login status (from last check_login call)."""
        conn = self._connections.get(shop_id)
        return conn.logged_in if conn else False

    def list_shops(self) -> list[dict[str, object]]:
        """List all configured shops with their status."""
        result = []
        for ep in config.CHROME_ENDPOINTS:
            conn = self._connections.get(ep.shop_id)
            result.append(
                {
                    "shop_id": ep.shop_id,
                    "shop_name": ep.shop_name,
                    "cdp_url": ep.cdp_url,
                    "vnc_url": ep.vnc_url,
                    "connected": conn is not None,
                    "logged_in": conn.logged_in if conn else False,
                }
            )
        return result

    # ── Dynamic shop registration ─────────────────────────

    def register_shop(self, shop_id: str) -> None:
        """Register a new shop's lock so it can be acquired.

        Call this after adding the endpoint to config.CHROME_ENDPOINTS.
        """
        if shop_id not in self._locks:
            self._locks[shop_id] = asyncio.Lock()
            print(f"[ChromePool] 已注册新店铺: {shop_id}")

    async def unregister_shop(self, shop_id: str) -> None:
        """Disconnect and remove a shop from the pool.

        Call this before removing the endpoint from config.CHROME_ENDPOINTS.
        """
        await self.disconnect(shop_id)
        self._locks.pop(shop_id, None)
        print(f"[ChromePool] 已注销店铺: {shop_id}")
