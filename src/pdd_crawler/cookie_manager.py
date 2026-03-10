"""Cookie manager for crawl4ai-based authentication."""

# pyright: reportMissingImports=false, reportMissingTypeStubs=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportUnknownArgumentType=false, reportUnusedCallResult=false, reportDeprecated=false

from __future__ import annotations

import asyncio
from pathlib import Path

from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig

from pdd_crawler import config
from pdd_crawler.home_scraper import get_shop_name


_PDD_HOME_URL = "https://mms.pinduoduo.com"
_PDD_LOGIN_INDICATOR = "/login"


def get_browser_config(
    headless: bool = True,
    cookie_path: Path | None = None,
    downloads_path: Path | None = None,
) -> BrowserConfig:
    """Build standard browser configuration for crawl4ai."""
    base = dict(config.BROWSER_CONFIG)
    extra_args = base.pop("extra_args", None)
    user_agent = base.pop("user_agent", None)
    _ = base.pop("headless", None)
    _ = base.pop("enable_stealth", None)

    return BrowserConfig(
        headless=headless,
        enable_stealth=True,
        storage_state=str(cookie_path) if cookie_path else None,
        user_agent=user_agent,
        headers=config.EXTRA_HEADERS,
        extra_args=extra_args,
        accept_downloads=downloads_path is not None,
        downloads_path=str(downloads_path) if downloads_path else None,
        **base,
    )


async def create_crawler(
    headless: bool = True,
    cookie_path: Path | None = None,
    downloads_path: Path | None = None,
) -> AsyncWebCrawler:
    """Create and start a configured crawl4ai crawler."""
    crawler = AsyncWebCrawler(config=get_browser_config(headless, cookie_path, downloads_path))
    await crawler.start()
    return crawler


async def _get_current_url(crawler: AsyncWebCrawler, session_id: str) -> str:
    """Get current page URL from a crawler session via the underlying Playwright page."""
    page, _ctx = await crawler.crawler_strategy.browser_manager.get_page(
        crawlerRunConfig=CrawlerRunConfig(session_id=session_id),
    )
    return page.url


async def _extract_shop_name_from_crawler(crawler: AsyncWebCrawler, session_id: str) -> str:
    """Extract shop name from active session page using crawl4ai."""
    current_url = await _get_current_url(crawler, session_id)
    if "mms.pinduoduo.com/home" not in current_url:
        await crawler.arun(
            url=config.PDD_HOME_URL,
            config=CrawlerRunConfig(session_id=session_id),
        )

    return await get_shop_name(crawler, session_id)


async def validate_cookies(cookie_path: Path) -> bool:
    """Validate storage_state by checking whether session is redirected to login."""
    cookie_path = Path(cookie_path)
    if not cookie_path.exists():
        print(f"[Cookie] 未找到 cookie 文件: {cookie_path}")
        return False

    session_id = "cookie_validate"
    crawler = await create_crawler(headless=True, cookie_path=cookie_path)
    try:
        await crawler.arun(
            url=_PDD_HOME_URL,
            config=CrawlerRunConfig(session_id=session_id),
        )
        current_url = await _get_current_url(crawler, session_id)
        if _PDD_LOGIN_INDICATOR in current_url:
            print("[Cookie] Cookie 已失效，需要重新登录")
            return False

        print("[Cookie] Cookie 验证通过")
        return True
    except Exception as e:
        print(f"[Cookie] 验证失败: {e}")
        return False
    finally:
        await crawler.close()


async def save_storage_state(
    crawler: AsyncWebCrawler,
    session_id: str,
    cookie_path: Path,
) -> None:
    """Save session storage_state JSON in Playwright format."""
    cookie_path = Path(cookie_path)
    cookie_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        strategy = crawler.crawler_strategy
        browser_manager = strategy.browser_manager
        
        # 首先尝试从现有会话获取上下文 - 这是最可靠的方式
        print("[Cookie] 从会话获取浏览器上下文...")
        _, ctx = await browser_manager.get_page(
            crawlerRunConfig=CrawlerRunConfig(session_id=session_id),
        )
        
        # 检查 ctx 是否有 storage_state 方法
        if not hasattr(ctx, 'storage_state'):
            # 如果当前对象没有 storage_state，尝试从 browser 获取第一个 context
            if hasattr(ctx, 'contexts') and ctx.contexts:
                ctx = ctx.contexts[0]
                if not hasattr(ctx, 'storage_state'):
                    raise RuntimeError("无法找到具有 storage_state 方法的 BrowserContext")
            else:
                raise RuntimeError("无法获取有效的 BrowserContext")
        
        await ctx.storage_state(path=str(cookie_path))
        if hasattr(strategy, 'logger') and strategy.logger:
            strategy.logger.info(
                message="Exported storage state to {path}",
                tag="INFO",
                params={"path": str(cookie_path)},
            )
        print(f"[Cookie] Cookie 已保存至: {cookie_path}")
    except AttributeError as e:
        print(f"[Cookie] 属性错误: {e}")
        raise
    except Exception as e:
        print(f"[Cookie] 导出 storage state 失败: {e}")
        raise


async def qr_login(
    shop_name: str | None = None,
    timeout: int = 120,
) -> tuple[Path, str]:
    """Perform QR login and persist storage_state as cookie file."""
    config.COOKIES_DIR.mkdir(parents=True, exist_ok=True)
    session_id = "qr_login"

    crawler = await create_crawler(headless=False)
    try:
        print("=" * 50)
        print("[登录] 正在打开拼多多商家后台登录页面...")
        print("[登录] 请使用拼多多 APP 扫描二维码登录")
        print(f"[登录] 超时时间: {timeout} 秒")
        print("=" * 50)

        await crawler.arun(
            url=_PDD_HOME_URL,
            config=CrawlerRunConfig(session_id=session_id),
        )

        elapsed = 0
        poll_interval = 2
        while elapsed < timeout:
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

            current_url = await _get_current_url(crawler, session_id)
            if _PDD_LOGIN_INDICATOR not in current_url:
                print("[登录] 登录成功！")

                if shop_name is None:
                    print("[登录] 正在提取店铺名称...")
                    shop_name = await _extract_shop_name_from_crawler(crawler, session_id)

                print(f"[登录] 店铺名称: {shop_name}")
                cookie_path = config.get_cookie_path(shop_name)
                await save_storage_state(crawler, session_id, cookie_path)
                print(f"[登录] Cookie 已保存至: {cookie_path}")
                return cookie_path, shop_name

            remaining = timeout - elapsed
            if remaining > 0 and remaining % 10 == 0:
                print(f"[登录] 等待扫码中... 剩余 {remaining} 秒")

        raise TimeoutError(f"[登录] 扫码登录超时（{timeout}秒），请重试")
    finally:
        await crawler.close()
        print("[登录] 登录浏览器已关闭")


async def ensure_authenticated(shop_name: str | None = None) -> tuple[Path, str]:
    """Ensure valid authentication and return cookie path + shop name."""
    if shop_name is not None:
        cookie_path = config.get_cookie_path(shop_name)
        if await validate_cookies(cookie_path):
            print(f"[Auth] 使用已有 cookie 认证成功 (店铺: {shop_name})")
            return cookie_path, shop_name
        print("[Auth] Cookie 已失效，切换到扫码登录")

    if shop_name is None:
        for candidate_path in sorted(config.COOKIES_DIR.glob("*_cookies.json")):
            print(f"[Auth] 尝试已有 cookie: {candidate_path.name}")
            if not await validate_cookies(candidate_path):
                print(f"[Auth] Cookie 已失效: {candidate_path.name}")
                continue

            crawler = await create_crawler(headless=True, cookie_path=candidate_path)
            session_id = "detect_shop_name"
            try:
                await crawler.arun(
                    url=config.PDD_HOME_URL,
                    config=CrawlerRunConfig(session_id=session_id),
                )
                detected_name = await _extract_shop_name_from_crawler(crawler, session_id)
                correct_path = config.get_cookie_path(detected_name)
                if correct_path != candidate_path:
                    await save_storage_state(crawler, session_id, correct_path)
                    print(f"[Auth] Cookie 重命名: {candidate_path.name} → {correct_path.name}")
                    try:
                        candidate_path.unlink()
                    except OSError:
                        pass

                print(f"[Auth] 使用已有 cookie 认证成功 (店铺: {detected_name})")
                return correct_path, detected_name
            finally:
                await crawler.close()

    print("[Auth] 启动扫码登录流程...")
    return await qr_login(shop_name=shop_name, timeout=config.QR_LOGIN_TIMEOUT)
