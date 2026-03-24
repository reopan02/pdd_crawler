"""Bill exporter using crawl4ai (no Selenium).

Exports cashier bills for tab 4001/4002, downloads files to the configured
downloads directory, and auto-extracts ZIP files.
"""

# pyright: reportMissingImports=false, reportMissingTypeStubs=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportUnknownArgumentType=false, reportUnusedCallResult=false, reportDeprecated=false, reportAttributeAccessIssue=false

from __future__ import annotations

import asyncio
import random
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path

from crawl4ai import AsyncWebCrawler, CrawlerRunConfig
from playwright.async_api import Page

import re

from pdd_crawler import config


def _extract_and_cleanup(zip_path: Path) -> Path | None:
    """Extract zip file to same directory, delete zip, return first extracted file."""
    if not zip_path.exists():
        return None

    extract_dir = zip_path.parent
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            extracted_files = zf.namelist()
            zf.extractall(extract_dir)
        zip_path.unlink()
        print(f"[账单] 已解压并删除压缩包: {zip_path.name}")
        if extracted_files:
            return extract_dir / extracted_files[0]
    except Exception as e:
        print(f"[账单] 解压失败: {e}")

    return None


def _result_text(result: object) -> str:
    """Best-effort conversion from crawler result to text."""
    if result is None:
        return ""
    if isinstance(result, str):
        return result

    extracted = getattr(result, "extracted_content", None)
    if isinstance(extracted, str) and extracted:
        return extracted

    markdown = getattr(result, "markdown", None)
    if isinstance(markdown, str) and markdown:
        return markdown

    html = getattr(result, "html", None)
    if isinstance(html, str) and html:
        return html

    return str(result)


def _is_blocked(body: str, url: str) -> bool:
    """Return True if anti-crawl/session-expired content is detected."""
    if "login" in url.lower():
        return True
    matched = [t for t in config.BLOCKED_TEXTS if t in body]
    if not matched:
        return False
    # Short pages with blocked text are definitely blocked (error/challenge pages)
    if len(body.strip()) < 1000:
        return True
    # Multiple blocked keywords strongly indicate an error page
    if len(matched) >= 2:
        return True
    # Single-keyword matches: only flag unambiguous error indicators
    # "关闭页面后重试" and "登录异常" only appear on error pages
    # "访问异常" and "验证身份" could appear in normal dashboard menus
    return any(kw in matched for kw in ["关闭页面后重试", "登录异常"])


def _log_blocked_reason(body: str, url: str, context: str) -> None:
    """Log which specific blocked pattern was matched for debugging."""
    matched = [t for t in config.BLOCKED_TEXTS if t in body]
    login_in_url = "login" in url.lower()
    print(
        f"[DEBUG-反爬] {context}: matched_texts={matched}, "
        f"login_in_url={login_in_url}, body_len={len(body)}, url={url[:100]}"
    )
    for kw in matched:
        idx = body.find(kw)
        if idx >= 0:
            start = max(0, idx - 40)
            end = min(len(body), idx + len(kw) + 40)
            snippet = body[start:end].replace("\n", " ")
            print(f"[DEBUG-反爬]   '{kw}' 上下文: ...{snippet}...")


async def _human_delay(lo: float = 1.0, hi: float = 2.5) -> None:
    """Sleep for a random human-like interval."""
    await asyncio.sleep(random.uniform(lo, hi))


async def _take_debug_screenshot(
    page, step_name: str, output_dir: Path | None = None
) -> Path | None:
    """Take a debug screenshot and save it to the output directory.

    Args:
        page: Playwright page object.
        step_name: Name of the navigation step for the filename.
        output_dir: Base output directory. If None, uses config.PROJECT_ROOT / "output" / "debug".

    Returns:
        Path to the saved screenshot file, or None if screenshot failed.
    """
    try:
        # Determine output directory
        if output_dir is None:
            debug_dir = config.PROJECT_ROOT / "output" / "debug"
        else:
            debug_dir = output_dir / "debug"

        # Create debug directory if it doesn't exist
        debug_dir.mkdir(parents=True, exist_ok=True)

        # Generate timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        screenshot_path = debug_dir / f"nav_{step_name}_{timestamp}.png"

        # Take screenshot
        await page.screenshot(path=screenshot_path)
        return screenshot_path
    except Exception as e:
        print(f"[账单-导航] 调试截图失败: {e}")
        return None


async def _dismiss_popups(page) -> None:
    """Dismiss common PDD popups/modals by clicking close buttons.

    Tries multiple selector patterns and text-based matching for close buttons.
    Best effort approach - never crashes.

    Args:
        page: Playwright page object.
    """
    try:
        # CSS selectors for common close buttons
        close_selectors = [
            '[class*="modal"] [class*="close"]',
            '[class*="dialog"] [class*="close"]',
            '[class*="overlay"] [class*="close"]',
            ".ant-modal-close",
        ]

        # Try each selector
        for selector in close_selectors:
            try:
                element = await page.query_selector(selector)
                if element:
                    await element.click()
                    await asyncio.sleep(0.5)
                    print("[账单-导航] 弹窗已关闭")
                    return
            except Exception:
                continue

        # Try text-based matching for Chinese close buttons
        close_texts = ["关闭", "我知道了", "稍后再说"]
        buttons = await page.query_selector_all("button, a, span, div")
        for button in buttons:
            try:
                text_content = await button.evaluate(
                    "el => (el.innerText || el.textContent || '').trim()"
                )
                if text_content and any(t in text_content for t in close_texts):
                    await button.click()
                    await asyncio.sleep(0.5)
                    print("[账单-导航] 弹窗已关闭")
                    return
            except Exception:
                continue
    except Exception as e:
        # Best effort - never crash the caller
        pass


async def _read_picker_date(page: Page) -> str:
    """Read the current date string from the date range input on the page.

    Returns the raw value like '2026-03-14 00:00:00 ~ 2026-03-14 23:59:59',
    or '' if not found.
    """
    for selector in ('[data-testid="beast-core-rangePicker-htmlInput"]',):
        loc = page.locator(selector)
        if await loc.count() > 0:
            val = await loc.first.input_value()
            if val:
                return val.strip()
    for placeholder in ("开始日期-结束日期", "请选择时间范围"):
        loc = page.get_by_placeholder(placeholder)
        if await loc.count() > 0:
            val = await loc.first.input_value()
            if val:
                return val.strip()
    return ""


def _parse_date_from_picker_value(picker_value: str) -> str:
    """Extract a YYYY-MM-DD date from the picker input value.

    The value looks like '2026-03-15 00:00:00 ~ 2026-03-15 23:59:59'.
    Returns the first date found, e.g. '2026-03-15', or '' on failure.
    """
    m = re.search(r"(\d{4}-\d{2}-\d{2})", picker_value)
    return m.group(1) if m else ""


async def _select_yesterday_date(
    page: Page, reference_today: date | None = None
) -> str:
    """Select yesterday's date range in the cashier bill date picker.

    Supports two picker variants:
      - Tab 4001: has a "昨天" shortcut button → click it (auto-closes picker).
      - Tab 4002: no "昨天" button → navigate calendar to the correct month,
        double-click yesterday's date cell, then click "确认".

    Yesterday is determined by the following priority:
      1. ``reference_today`` — a trusted date obtained from a previous tab
         (e.g. 4001's picker which always shows today).
      2. The PDD page's current date display — but ONLY if it matches the
         system date.  Some tabs (e.g. 4002) pre-fill a date that is NOT
         today, which would produce a wrong "yesterday".
      3. ``date.today()`` as a last resort.

    After the date is set, clicks "查询" to refresh the table.

    Args:
        page: Playwright page object.
        reference_today: Trusted "today" date from a previous tab.  When
            provided, the picker's own date is ignored for computing
            yesterday (it is still read for logging).

    Returns:
        The YYYY-MM-DD date string that was selected (e.g. '2026-03-14'),
        or '' if selection failed.
    """
    try:
        # ── Determine "today" reliably ──
        # The picker value is NOT always today (4002 may show month-start).
        # We trust: reference_today > picker (only if == system today) > system today.
        current_picker_value = await _read_picker_date(page)
        picker_date_str = _parse_date_from_picker_value(current_picker_value)
        system_today = date.today()

        if reference_today is not None:
            pdd_today = reference_today
            print(
                f"[账单-日期] 使用参考日期(4001): {pdd_today.isoformat()}"
                f" (页面picker值: {picker_date_str or '无'})"
            )
        elif picker_date_str:
            picker_date = datetime.strptime(picker_date_str, "%Y-%m-%d").date()
            if picker_date == system_today:
                pdd_today = picker_date
                print(
                    f"[账单-日期] PDD页面当前日期: {picker_date_str}, "
                    f"与系统日期一致, 使用此日期"
                )
            else:
                pdd_today = system_today
                print(
                    f"[账单-日期] PDD页面日期: {picker_date_str} "
                    f"≠ 系统日期: {system_today.isoformat()}, "
                    f"picker值不可信, 使用系统日期"
                )
        else:
            pdd_today = system_today
            print(
                f"[账单-日期] 无法从页面读取日期, "
                f"使用系统日期: {system_today.isoformat()}"
            )

        pdd_yesterday = pdd_today - timedelta(days=1)
        print(
            f"[账单-日期] 确定今天: {pdd_today.isoformat()}, "
            f"目标昨天: {pdd_yesterday.isoformat()}"
        )

        # 1) Click the date range input to open the picker
        date_input = page.locator('[data-testid="beast-core-rangePicker-htmlInput"]')
        if await date_input.count() == 0:
            date_input = page.get_by_placeholder("开始日期-结束日期")
        if await date_input.count() == 0:
            date_input = page.get_by_placeholder("请选择时间范围")
        if await date_input.count() == 0:
            print("[账单-日期] 未找到日期选择器输入框")
            return ""

        await date_input.first.click()
        await _human_delay(0.5, 1.0)

        # 2) Try the "昨天" shortcut button first (available on 4001)
        yesterday_btn = page.locator("button:has-text('昨天')")
        if await yesterday_btn.count() > 0:
            await yesterday_btn.first.click()
            await _human_delay(0.5, 1.0)
            print("[账单-日期] 已点击'昨天'快捷按钮 (4001模式)")

            # Click "确认" if picker is still open
            confirm_btn = page.locator("button:has-text('确认')")
            if await confirm_btn.count() > 0:
                try:
                    await confirm_btn.first.click(timeout=2000)
                    await _human_delay(0.3, 0.6)
                except Exception:
                    pass
        else:
            # 4002 mode: no "昨天" button → set date via JS injection.
            # The calendar UI is a custom Beast component whose DOM structure
            # is unpredictable (header selectors return empty, month navigation
            # is unreliable).  Instead we directly set the hidden input value
            # and trigger React's change pipeline.
            print("[账单-日期] 无'昨天'按钮, 使用JS注入模式 (4002模式)")

            # Close the picker popup first (Escape key)
            await page.keyboard.press("Escape")
            await _human_delay(0.3, 0.6)

            yesterday_str = pdd_yesterday.isoformat()  # e.g. "2026-03-15"
            target_value = f"{yesterday_str} 00:00:00 ~ {yesterday_str} 23:59:59"

            # Find the date input element
            input_sel = '[data-testid="beast-core-rangePicker-htmlInput"]'
            input_loc = page.locator(input_sel)
            if await input_loc.count() == 0:
                # Fallback selectors
                for ph in ("开始日期-结束日期", "请选择时间范围"):
                    input_loc = page.get_by_placeholder(ph)
                    if await input_loc.count() > 0:
                        break

            if await input_loc.count() == 0:
                print("[账单-日期] 4002模式: 未找到日期输入框")
                return ""

            # Set value via JS and trigger React change events.
            # React overrides the native value setter, so we must use the
            # native HTMLInputElement.prototype setter to bypass it, then
            # dispatch 'input' and 'change' events.
            js_set_date = (
                """
                (el) => {
                    const nativeSetter = Object.getOwnPropertyDescriptor(
                        window.HTMLInputElement.prototype, 'value'
                    ).set;
                    nativeSetter.call(el, '%s');
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                }
            """
                % target_value
            )

            await input_loc.first.evaluate(js_set_date)
            await _human_delay(0.5, 1.0)
            print(f"[账单-日期] 已通过JS设置日期输入值: {target_value}")

        # 3) Click "查询" to apply the date filter
        query_btn = page.locator("button:has-text('查询')")
        if await query_btn.count() > 0:
            await query_btn.first.click()
            await _human_delay(1.0, 2.0)
            print("[账单-日期] 已点击'查询', 日期已切换为昨天")
        else:
            print("[账单-日期] 未找到'查询'按钮")

        # 4) Read back the actual selected date from the input
        final_value = await _read_picker_date(page)
        selected_date = _parse_date_from_picker_value(final_value)
        if selected_date:
            print(f"[账单-日期] 最终选中日期: {selected_date}")
        else:
            # Fallback: use the computed yesterday
            selected_date = pdd_yesterday.isoformat() if pdd_yesterday else ""
            print(f"[账单-日期] 无法读回日期, 使用计算值: {selected_date}")

        return selected_date
    except Exception as e:
        print(f"[账单-日期] 选择昨天日期失败: {e}")
        return ""


async def _pw_click(
    page: Page,
    selectors: list[str],
    texts: list[str],
    timeout_ms: int = 5000,
) -> bool:
    """Click element using Playwright native API.

    Priority:
        1. Try CSS selector (e.g., #exportBalance-btn)
        2. Fall back to button:has-text('...') text matching

    Args:
        page: Playwright Page object
        selectors: List of CSS selectors to try first
        texts: List of text patterns to match as fallback
        timeout_ms: Timeout for waiting for element

    Returns:
        True if click succeeded, False otherwise
    """
    for selector in selectors:
        try:
            locator = page.locator(selector)
            if await locator.count() > 0:
                await locator.first.scroll_into_view_if_needed()
                await locator.first.click(timeout=timeout_ms)
                print(f"[_pw_click] Clicked via selector: {selector}")
                return True
        except Exception:
            continue

    for text in texts:
        try:
            button_locator = page.locator(f"button:has-text('{text}')")
            if await button_locator.count() > 0:
                await button_locator.first.scroll_into_view_if_needed()
                await button_locator.first.click(timeout=timeout_ms)
                print(f"[_pw_click] Clicked button with text: {text}")
                return True
        except Exception:
            continue

        try:
            link_locator = page.locator(f"a:has-text('{text}')")
            if await link_locator.count() > 0:
                await link_locator.first.scroll_into_view_if_needed()
                await link_locator.first.click(timeout=timeout_ms)
                print(f"[_pw_click] Clicked link with text: {text}")
                return True
        except Exception:
            continue

    print(f"[_pw_click] Failed to click: selectors={selectors}, texts={texts}")
    return False


async def _wait_for_new_download(
    output_dir: Path,
    before: set[Path],
    timeout_s: int,
) -> Path | None:
    """Wait until a new completed file appears in output_dir."""
    deadline = asyncio.get_running_loop().time() + timeout_s
    while asyncio.get_running_loop().time() < deadline:
        if output_dir.exists():
            current = set(output_dir.iterdir())
            new_files = sorted(
                [p for p in current - before if p.is_file()],
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            for candidate in new_files:
                if candidate.suffix.lower() in {".crdownload", ".tmp", ".part"}:
                    continue
                size_1 = candidate.stat().st_size
                await asyncio.sleep(0.8)
                if not candidate.exists():
                    continue
                size_2 = candidate.stat().st_size
                if size_1 == size_2:
                    return candidate

        await asyncio.sleep(1.0)
    return None


async def _navigate_to_bill_tab(
    crawler: AsyncWebCrawler,
    session_id: str,
    tab_url: str,
) -> bool:
    """Navigate to cashier bill tab via mms SSO proxy.

    Direct access to cashier.pinduoduo.com triggers "登录异常" because
    the cashier domain requires its own session established via an SSO
    ticket from mms.  The correct flow is:

      1. Navigate to mms.pinduoduo.com/cashier/finance/payment-bills
         (the mms-side proxy page for cashier).
      2. mms server generates an auth ticket and the page redirects to
         cashier.pinduoduo.com/main/auth?ticket=<hex> which validates
         the ticket via /sherlock/api/auth/checkTicketV2 and sets
         cashier session cookies.
      3. The page finally lands on cashier with a valid session.
      4. Once the session is established we can navigate to any cashier
         tab URL directly.
    """
    last_page = None

    for attempt in range(1, config.NAV_MAX_RETRIES + 1):
        try:
            page, _ctx = await crawler.crawler_strategy.browser_manager.get_page(  # type: ignore[union-attr]
                crawlerRunConfig=CrawlerRunConfig(session_id=session_id),
            )
            last_page = page

            # ── Step 1: Navigate through mms proxy to establish cashier session via SSO ticket ──
            print(
                f"[账单-导航] 第{attempt}次尝试, Step 1: 通过mms代理页建立cashier会话 (SSO)"
            )
            try:
                await page.goto(
                    config.MMS_CASHIER_PROXY_URL,
                    wait_until="domcontentloaded",
                    timeout=30000,
                )
            except Exception as e:
                print(f"[账单-导航] 第{attempt}次尝试, Step 1访问mms代理页失败: {e}")

            await _human_delay(3.0, 5.0)

            try:
                await page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass

            sso_url = page.url or ""
            if "cashier.pinduoduo.com" not in sso_url:
                print(
                    f"[账单-导航] 第{attempt}次尝试, Step 1: SSO重定向未到达cashier: {sso_url}"
                )
                continue
            print(
                f"[账单-导航] 第{attempt}次尝试, Step 1: SSO完成, 已到达cashier: {sso_url}"
            )

            await _dismiss_popups(page)
            await _take_debug_screenshot(page, f"cashier_sso_attempt{attempt}", None)

            # ── Step 2: Navigate to the specific bill tab ──
            # If we already landed on the target tab, skip the extra navigation.
            if tab_url in sso_url:
                print(f"[账单-导航] 第{attempt}次尝试, Step 2: SSO已直接到达目标页面")
            else:
                print(f"[账单-导航] 第{attempt}次尝试, Step 2: 导航到目标账单页")
                await _human_delay(1.0, 2.0)
                try:
                    await page.goto(
                        tab_url, wait_until="domcontentloaded", timeout=30000
                    )
                except Exception as e:
                    print(f"[账单-导航] 第{attempt}次尝试, Step 2导航失败: {e}")

                await _human_delay(2.0, 4.0)
                try:
                    await page.wait_for_load_state("networkidle", timeout=15000)
                except Exception:
                    pass

            final_url = page.url or ""
            if "cashier.pinduoduo.com" not in final_url:
                print(
                    f"[账单-导航] 第{attempt}次尝试, Step 2: 未能停留在cashier域名: {final_url}"
                )
                continue

            # ── Step 3: Verify no anti-bot block ──
            print(f"[账单-导航] 第{attempt}次尝试, Step 3: 验证页面正常: {final_url}")

            body_text = await page.evaluate("document.body.innerText || ''") or ""
            if _is_blocked(body_text, final_url):
                _log_blocked_reason(
                    body_text, final_url, f"bill_verify_attempt_{attempt}"
                )
                print(f"[账单-导航] 第{attempt}次尝试, Step 3: 页面疑似风控，准备重试")
                continue

            await _take_debug_screenshot(page, f"bill_success_attempt{attempt}", None)
            print(f"[账单-导航] ✅ 第{attempt}次尝试成功, 已到达账单页面: {final_url}")
            return True

        except Exception as e:
            print(f"[账单-导航] 第{attempt}次尝试异常: {e}")
        finally:
            if attempt < config.NAV_MAX_RETRIES:
                backoff = config.NAV_RETRY_BASE_DELAY * (2 ** (attempt - 1))
                print(f"[账单-导航] 第{attempt}次尝试失败，{backoff:.1f}s后重试")
                await asyncio.sleep(backoff)

    if last_page is not None:
        await _take_debug_screenshot(last_page, "bill_all_retries_failed", None)
    print(f"[账单-导航] ❌ 导航失败，已重试{config.NAV_MAX_RETRIES}次")
    return False


async def export_single_bill(
    crawler: AsyncWebCrawler,
    session_id: str,
    tab_url: str,
    output_dir: Path,
    reference_today: date | None = None,
) -> tuple[Path | None, date | None]:
    """Export a single tab bill and return downloaded/extracted file path.

    Flow:
    1. Navigate to bill tab via SSO proxy
    2. Click export button → new tab opens automatically to export history page
    3. In new tab, click download button (#downloadBalance-btn-0)
    4. Wait for file download and extract if ZIP

    Returns:
        A tuple of (downloaded_file_path, resolved_today_date).
        The resolved_today_date can be passed to subsequent tabs as
        ``reference_today`` so they don't rely on their own picker value.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    ok = await _navigate_to_bill_tab(crawler, session_id, tab_url)
    if not ok:
        print(f"⚠️ 反爬机制触发，跳过: {tab_url}")
        return None, None

    # Get Playwright page and context for subsequent operations
    browser_manager = crawler.crawler_strategy.browser_manager  # type: ignore[union-attr]
    page, context = await browser_manager.get_page(
        crawlerRunConfig=CrawlerRunConfig(session_id=session_id),
    )

    # 0) Select yesterday's date range before exporting
    selected_date = await _select_yesterday_date(page, reference_today)
    # Derive the resolved "today" from the selected date so the caller can
    # pass it to subsequent tabs.
    resolved_today: date | None = None
    if selected_date:
        try:
            resolved_today = datetime.strptime(
                selected_date, "%Y-%m-%d"
            ).date() + timedelta(days=1)
        except ValueError:
            pass
    if not selected_date:
        print("[账单] 日期选择失败，将使用页面默认日期范围导出")

    # 1) Click export button - this opens a new tab automatically
    export_selectors = [
        "#exportBalance-btn",
        'button[class*="export"]',
        '[class*="export"] button',
    ]

    # Try to capture a new tab opened by the export button.
    # Some PDD cashier builds open a new tab; others navigate in-place or do nothing.
    # Strategy:
    #   1. Start expect_page listener BEFORE clicking.
    #   2. If a new tab appears within 10 s → use it.
    #   3. If no new tab → fall back to direct navigation of export-history URL
    #      in the current page (same behaviour as the existing URL-mismatch fallback).
    new_page = None

    try:
        async with context.expect_page(timeout=10000) as page_info:
            clicked = await _pw_click(page, export_selectors, ["导出账单", "导出"])
            if not clicked:
                print("[账单] 未找到导出按钮")
                return None, resolved_today
            print("[账单] 已点击导出按钮，等待新标签页打开...")

        new_page = await page_info.value
        print(f"[账单] 新标签页已打开: {new_page.url}")

    except Exception as e:
        print(f"[账单] 未检测到新标签页 ({e})，降级为当前页面导航")
        # Click the button again best-effort (may already be clicked above)
        await _pw_click(page, export_selectors, ["导出账单", "导出"])
        await _human_delay(1.5, 2.5)
        # Resolve export-history URL for this tab
        _export_history_url = config.BILL_EXPORT_HISTORY_MAP.get(tab_url)
        if not _export_history_url:
            _tab_part = (
                tab_url.split("tab=")[1].split("&")[0] if "tab=" in tab_url else "4001"
            )
            _export_history_url = (
                "https://cashier.pinduoduo.com/main/bills/export-history"
                f"?tab={_tab_part}&__app_code=113"
            )
        try:
            await page.goto(
                _export_history_url, wait_until="domcontentloaded", timeout=30000
            )
            await _human_delay(1.0, 2.0)
        except Exception as nav_err:
            print(f"[账单] 导航到导出历史页失败: {nav_err}")
            return None, resolved_today
        new_page = page  # reuse current page

    # Wait for the page to load
    try:
        await new_page.wait_for_load_state("domcontentloaded", timeout=15000)
    except Exception:
        pass
    await _human_delay(1.0, 2.0)

    # Verify we're on the export history page; navigate there if not
    current_url = new_page.url or ""
    if "export-history" not in current_url:
        print(f"[账单] 当前页面不是导出历史页: {current_url}，直接导航")
        export_history_url = config.BILL_EXPORT_HISTORY_MAP.get(tab_url)
        if not export_history_url:
            tab_part = (
                tab_url.split("tab=")[1].split("&")[0] if "tab=" in tab_url else "4001"
            )
            export_history_url = (
                "https://cashier.pinduoduo.com/main/bills/export-history"
                f"?tab={tab_part}&__app_code=113"
            )
        try:
            await new_page.goto(
                export_history_url, wait_until="domcontentloaded", timeout=30000
            )
            await _human_delay(1.0, 2.0)
        except Exception as e:
            print(f"[账单] 导航到导出历史页失败: {e}")
            return None, resolved_today

    # Check for anti-bot blocking
    history_body = await new_page.evaluate("document.body.innerText || ''") or ""
    if _is_blocked(history_body, current_url):
        _log_blocked_reason(history_body, current_url, "export_history")
        print(f"⚠️ 导出记录页被拦截，跳过: {tab_url}")
        return None, resolved_today

    await _take_debug_screenshot(new_page, "export_history_page", output_dir)

    # 2) Click download button in new tab (#downloadBalance-btn-0)
    # Use Playwright's expect_download for reliable download handling
    print("[账单] 寻找下载按钮...")

    # Try specific download button ID first, then fallback to other selectors
    download_selectors = [
        "#downloadBalance-btn-0",
        "[id^='downloadBalance-btn']",
        'button:has-text("下载账单")',
        'button:has-text("下载")',
        '[href*="download"]',
        "a[download]",
        'button[class*="download"]',
    ]

    # Wait for download event when clicking the button
    try:
        async with new_page.expect_download(timeout=60000) as download_info:
            clicked_download = await _pw_click(
                new_page, download_selectors, ["下载账单", "下载"]
            )

            if not clicked_download:
                print("[账单] 未找到下载按钮，尝试等待页面加载...")
                await _human_delay(2.0, 3.0)
                clicked_download = await _pw_click(
                    new_page, download_selectors, ["下载账单", "下载"]
                )

            if not clicked_download:
                print("[账单] 下载按钮未找到")
                return None, resolved_today

            print("[账单] 已点击下载按钮，等待下载完成...")

        download = await download_info.value
        suggested_name = download.suggested_filename
        print(f"[账单] 下载文件名: {suggested_name}")

        # Save to output directory
        download_path = output_dir / suggested_name
        await download.save_as(download_path)
        downloaded_file = download_path

    except Exception as e:
        print(f"[账单] 下载事件捕获失败，尝试轮询方式: {e}")
        # Fallback to polling method
        before_files = set(output_dir.iterdir()) if output_dir.exists() else set()

        clicked_download = await _pw_click(
            new_page, download_selectors, ["下载账单", "下载"]
        )
        if not clicked_download:
            print("[账单] 下载按钮未找到")
            return None, resolved_today

        print("[账单] 已点击下载按钮，等待文件出现...")

        downloaded_file = await _wait_for_new_download(
            output_dir=output_dir,
            before=before_files,
            timeout_s=max(10, config.DOWNLOAD_TIMEOUT // 1000),
        )

        if downloaded_file is None:
            print("[账单] 下载超时")
            return None, resolved_today

    print(f"✅ 账单已下载: {downloaded_file}")
    if downloaded_file.suffix.lower() == ".zip":
        extracted = _extract_and_cleanup(downloaded_file)
        if extracted:
            print(f"✅ 已解压: {extracted}")
            return extracted, resolved_today
    return downloaded_file, resolved_today


async def export_all_bills(
    crawler: AsyncWebCrawler,
    session_id: str,
    cookie_path: Path,
    output_dir: Path,
) -> list[Path]:
    """Export bills from tab 4001 and 4002.

    4001 is exported first; its resolved "today" date is passed to 4002 as
    ``reference_today`` so that 4002 does not rely on its own (potentially
    incorrect) picker default value.

    Notes:
        - `crawler` should be created with `BrowserConfig(accept_downloads=True,
          downloads_path=str(output_dir), storage_state=str(cookie_path), ...)`
        - Uses a fresh session_id suffix per tab to avoid session contamination
          when one tab triggers anti-bot detection.
    """
    _ = cookie_path
    output_dir.mkdir(parents=True, exist_ok=True)

    downloaded: list[Path] = []
    reference_today: date | None = None  # populated by 4001, used by 4002

    for i, tab_url in enumerate(
        [config.CASHIER_BILL_4001_URL, config.CASHIER_BILL_4002_URL]
    ):
        # Use a unique session per tab to avoid contamination from blocked attempts
        tab_session_id = f"{session_id}_tab{i}"
        try:
            file_path, resolved_today = await export_single_bill(
                crawler, tab_session_id, tab_url, output_dir, reference_today
            )
            if file_path is not None:
                downloaded.append(file_path)
            # Capture the first tab's resolved date for subsequent tabs
            if resolved_today is not None and reference_today is None:
                reference_today = resolved_today
                print(
                    f"[账单] 4001确认今天日期: {reference_today.isoformat()}, "
                    f"后续tab将使用此日期"
                )
        except Exception as e:
            print(f"⚠️ 导出失败: {e}")

    print(f"📊 共下载 {len(downloaded)} 个账单文件")
    return downloaded
