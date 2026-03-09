"""Bill exporter for downloading cashier bills from PDD.

PDD's cashier.pinduoduo.com has aggressive anti-crawl that blocks direct
page.goto() navigation and even window.open() — it validates the session
origin and browser fingerprint.

Strategy: from the mms.pinduoduo.com home page, we click the "账房" /
"资金管理" sidebar link to let PDD's SPA handle the cross-domain
navigation naturally.  If the sidebar click approach fails, we fall back
to direct goto with extra anti-detection headers.
"""

from datetime import datetime
from pathlib import Path
from typing import Optional
import random

from playwright.async_api import BrowserContext, Page

from pdd_crawler import config


def _is_blocked(body: str, url: str) -> bool:
    """Return True if the page shows anti-crawl / session-expired content."""
    blocked_texts = ["登录异常", "关闭页面后重试", "访问异常", "验证身份"]
    return any(t in body for t in blocked_texts) or "login" in url.lower()


async def _navigate_to_cashier_via_sidebar(page: Page) -> Optional[Page]:
    """Try to reach cashier by clicking through the mms sidebar.

    PDD's mms sidebar contains links like "账房" / "资金管理" / "账单"
    that open cashier.pinduoduo.com in an iframe or via SPA routing.
    Clicking these is the most natural way and avoids anti-crawl.
    """
    # First make sure we're on mms home
    if "mms.pinduoduo.com" not in page.url or "/login" in page.url:
        await page.goto(
            config.PDD_HOME_URL,
            wait_until="domcontentloaded",
            timeout=config.PAGE_LOAD_TIMEOUT,
        )
        await page.wait_for_timeout(5000)

    # Try to find and click billing/cashier related sidebar links
    sidebar_selectors = [
        'text="账房"',
        'text="资金管理"',
        'text="资金概览"',
        'text="账单"',
        'a[href*="cashier"]',
        '[class*="menu"] >> text="账房"',
        '[class*="nav"] >> text="账房"',
        '[class*="sidebar"] >> text="账房"',
    ]

    for selector in sidebar_selectors:
        try:
            link = page.locator(selector).first
            if await link.is_visible(timeout=2000):
                print(f"[账单] 找到侧边栏入口: {selector}")
                await link.click()
                await page.wait_for_timeout(3000)
                return page
        except Exception:
            continue

    return None


async def _navigate_to_bill_tab(
    context: BrowserContext, page: Page, tab_url: str
) -> Page:
    """Navigate to a specific cashier bill tab.

    Tries multiple strategies:
    1. Click through mms sidebar (most natural, avoids anti-crawl)
    2. Use JavaScript navigation from mms context
    3. Open in a new tab via window.open from mms
    4. Direct goto as last resort

    Returns the page that has the bill content (may be the same page
    or a new popup tab).
    """
    # Ensure we start from mms home
    if "mms.pinduoduo.com" not in page.url or "/login" in page.url:
        await page.goto(
            config.PDD_HOME_URL,
            wait_until="domcontentloaded",
            timeout=config.PAGE_LOAD_TIMEOUT,
        )
        await page.wait_for_timeout(random.randint(4000, 6000))

    # --- Strategy 1: Navigate through mms sidebar first ----------------------
    # Clicking the cashier/billing link in the sidebar is the most natural
    # browsing flow.  It lets PDD's SPA set up the cross-domain session
    # (cookies, referrer chain) before we hit the cashier URL.
    sidebar_page = await _navigate_to_cashier_via_sidebar(page)

    if sidebar_page is not None:
        await page.wait_for_timeout(random.randint(2000, 4000))

        # Sidebar click may have navigated the page to cashier
        if "cashier" in page.url:
            print(f"[账单] 侧边栏导航成功，跳转到具体账单页...")
            await page.evaluate(f'location.href = "{tab_url}"')
            try:
                await page.wait_for_load_state(
                    "domcontentloaded", timeout=config.PAGE_LOAD_TIMEOUT
                )
            except Exception:
                pass
            await page.wait_for_timeout(random.randint(5000, 8000))

            body = await page.text_content("body") or ""
            if not _is_blocked(body, page.url):
                return page

        # Sidebar click may have opened a new tab
        for p in context.pages:
            if p is not page and "cashier" in p.url:
                body = await p.text_content("body") or ""
                if not _is_blocked(body, p.url):
                    print(f"[账单] 侧边栏打开了新标签页，跳转到具体账单页...")
                    await p.evaluate(f'location.href = "{tab_url}"')
                    try:
                        await p.wait_for_load_state(
                            "domcontentloaded", timeout=config.PAGE_LOAD_TIMEOUT
                        )
                    except Exception:
                        pass
                    await p.wait_for_timeout(random.randint(5000, 8000))
                    body = await p.text_content("body") or ""
                    if not _is_blocked(body, p.url):
                        return p
                    await p.close()
                break

        # Return to mms for next strategy
        if "mms.pinduoduo.com" not in page.url:
            await page.goto(
                config.PDD_HOME_URL,
                wait_until="domcontentloaded",
                timeout=config.PAGE_LOAD_TIMEOUT,
            )
            await page.wait_for_timeout(random.randint(2000, 4000))

    # --- Strategy 2: JS location.href from the mms page context --------------
    # Preserves document.referrer and opener chain better than page.goto().
    print(f"[账单] 通过JS跳转访问账单页...")
    await page.evaluate(f'location.href = "{tab_url}"')
    try:
        await page.wait_for_load_state(
            "domcontentloaded", timeout=config.PAGE_LOAD_TIMEOUT
        )
    except Exception:
        pass
    await page.wait_for_timeout(random.randint(5000, 8000))

    body = await page.text_content("body") or ""
    if not _is_blocked(body, page.url):
        return page

    # --- Strategy 3: window.open in a new tab from the mms context -----------
    print("[账单] JS跳转被拦截，尝试新标签页方式...")
    await page.goto(
        config.PDD_HOME_URL,
        wait_until="domcontentloaded",
        timeout=config.PAGE_LOAD_TIMEOUT,
    )
    await page.wait_for_timeout(random.randint(2000, 4000))

    try:
        async with context.expect_page(timeout=15000) as new_page_info:
            await page.evaluate(f'window.open("{tab_url}")')
        cashier_page = await new_page_info.value
        await cashier_page.wait_for_load_state("domcontentloaded")
        await cashier_page.wait_for_timeout(random.randint(5000, 8000))

        body = await cashier_page.text_content("body") or ""
        if not _is_blocked(body, cashier_page.url):
            return cashier_page
        await cashier_page.close()
    except Exception as e:
        print(f"[账单] 新标签页方式失败: {e}")

    # --- Strategy 4: Direct goto as last resort ------------------------------
    print("[账单] 尝试直接访问...")
    await page.goto(
        tab_url,
        wait_until="domcontentloaded",
        timeout=config.PAGE_LOAD_TIMEOUT,
    )
    await page.wait_for_timeout(random.randint(5000, 8000))
    return page


async def export_single_bill(
    context: BrowserContext, opener_page: Page, tab_url: str, download_dir: Path
) -> Optional[Path]:
    """Open a cashier bill tab and download the bill export.

    Args:
        context: BrowserContext (needed for new tab handling).
        opener_page: A page currently on mms.pinduoduo.com.
        tab_url: Full URL to the cashier bill tab.
        download_dir: Directory to save downloaded files.

    Returns:
        Path to the downloaded file, or None if export failed.
    """
    download_dir.mkdir(parents=True, exist_ok=True)

    bill_page = await _navigate_to_bill_tab(context, opener_page, tab_url)
    # Track whether we opened a separate page that needs closing
    is_separate_page = bill_page is not opener_page

    try:
        # Check if we're blocked
        body = await bill_page.text_content("body") or ""
        if _is_blocked(body, bill_page.url):
            print(f"⚠️ 反爬机制触发，跳过: {tab_url}")
            return None

        # Locate "导出账单" button
        button = None
        selectors = [
            lambda: bill_page.get_by_text("导出账单"),
            lambda: bill_page.get_by_role("button", name="导出账单"),
            lambda: bill_page.locator('button:has-text("导出")'),
            lambda: bill_page.locator('[class*="export"], [class*="download"]'),
        ]

        for selector_fn in selectors:
            try:
                candidate = selector_fn()
                await candidate.first.wait_for(state="visible", timeout=10000)
                button = candidate.first
                break
            except Exception:
                continue

        if button is None:
            print(f"⚠️ 未找到导出按钮，跳过: {tab_url}")
            return None

        await button.scroll_into_view_if_needed()
        await button.click()
        print("[账单] 已点击导出按钮，等待弹窗...")
        await bill_page.wait_for_timeout(3000)

        # --- Phase 1: Handle export confirmation modal ----------------------
        # After clicking "导出账单", a modal appears to configure the export.
        # We need to click the confirm button inside it.
        modal_confirm_selectors = [
            'button:has-text("确认导出")',
            'button:has-text("确认")',
            'button:has-text("确定")',
            'button:has-text("生成")',
            'button:has-text("导出")',
            '[class*="modal"] button[class*="primary"]',
            '[class*="Modal"] button[class*="primary"]',
            '[role="dialog"] button[class*="primary"]',
        ]

        for selector in modal_confirm_selectors:
            try:
                btn = bill_page.locator(selector).first
                if await btn.is_visible(timeout=2000):
                    print(f"[账单] 点击确认按钮: {selector}")
                    await btn.click()
                    await bill_page.wait_for_timeout(3000)
                    break
            except Exception:
                continue

        # --- Phase 2: Navigate to export-history page to download ------------
        # PDD generates the bill server-side.  The downloadable file appears
        # on the export-history page, not on the bills page itself.
        export_history_url = config.BILL_EXPORT_HISTORY_MAP.get(tab_url)
        if not export_history_url:
            # Build it dynamically from the tab parameter
            tab_part = (
                tab_url.split("tab=")[1].split("&")[0] if "tab=" in tab_url else "4001"
            )
            export_history_url = (
                f"https://cashier.pinduoduo.com/main/bills/export-history"
                f"?tab={tab_part}&__app_code=113"
            )

        print(f"[账单] 跳转到导出记录页: {export_history_url}")
        await bill_page.evaluate(f'location.href = "{export_history_url}"')
        try:
            await bill_page.wait_for_load_state(
                "domcontentloaded", timeout=config.PAGE_LOAD_TIMEOUT
            )
        except Exception:
            pass
        await bill_page.wait_for_timeout(8000)

        # --- Phase 3: Find and click the download button/link ----------------
        # The export-history page lists previously generated exports with
        # "下载" links.  We click the first (most recent) one.
        download_selectors = [
            'a:has-text("下载")',
            'button:has-text("下载")',
            'text="下载"',
            'a[href*="download"]',
            '[class*="download"]',
        ]

        for selector in download_selectors:
            try:
                dl_link = bill_page.locator(selector).first
                if await dl_link.is_visible(timeout=10000):
                    print(f"[账单] 找到下载按钮: {selector}")
                    async with bill_page.expect_download(
                        timeout=config.DOWNLOAD_TIMEOUT
                    ) as download_info:
                        await dl_link.click()
                    download = await download_info.value

                    suggested = download.suggested_filename
                    if not suggested:
                        tab_part = (
                            tab_url.split("tab=")[1][:4]
                            if "tab=" in tab_url
                            else "unknown"
                        )
                        suggested = f"bill_{tab_part}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

                    filepath = download_dir / suggested
                    await download.save_as(str(filepath))

                    if filepath.stat().st_size > 0:
                        print(f"✅ 账单已下载: {filepath}")
                    else:
                        print(f"⚠️ 下载文件为空: {filepath}")
                    return filepath
            except Exception as e:
                print(f"[账单] 下载尝试失败 ({selector}): {e}")
                continue

        # --- Phase 4: Failed — save debug screenshot -------------------------
        print(f"⚠️ 未能在导出记录页找到下载按钮: {tab_url}")
        try:
            tab_part = tab_url.split("tab=")[1][:4] if "tab=" in tab_url else "unknown"
            debug_path = download_dir / f"_debug_export_history_{tab_part}.png"
            await bill_page.screenshot(path=str(debug_path))
            print(f"[账单] 导出记录页截图: {debug_path}")
        except Exception:
            pass
        return None

    finally:
        if is_separate_page:
            await bill_page.close()


async def export_all_bills(
    context: BrowserContext, page: Page, download_dir: Path
) -> list[Path]:
    """Download bills from all configured cashier bill tabs.

    Args:
        context: BrowserContext.
        page: An mms.pinduoduo.com page.
        download_dir: Directory to save downloaded files.

    Returns:
        List of paths to successfully downloaded files.
    """
    downloaded: list[Path] = []

    for url in [config.CASHIER_BILL_4001_URL, config.CASHIER_BILL_4002_URL]:
        try:
            result = await export_single_bill(context, page, url, download_dir)
            if result is not None:
                downloaded.append(result)
        except Exception as e:
            print(f"⚠️ 导出失败 ({url}): {e}")

        # Navigate back to mms between exports so each starts from
        # a clean mms session context
        try:
            if "mms.pinduoduo.com" not in page.url:
                await page.goto(
                    config.PDD_HOME_URL,
                    wait_until="domcontentloaded",
                    timeout=config.PAGE_LOAD_TIMEOUT,
                )
                await page.wait_for_timeout(3000)
        except Exception:
            pass

    print(f"📊 共下载 {len(downloaded)} 个账单文件")
    return downloaded
