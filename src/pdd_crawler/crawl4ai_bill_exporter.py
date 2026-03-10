"""Bill exporter using crawl4ai (no Selenium).

Exports cashier bills for tab 4001/4002, downloads files to the configured
downloads directory, and auto-extracts ZIP files.
"""

# pyright: reportMissingImports=false, reportMissingTypeStubs=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportUnknownArgumentType=false, reportUnusedCallResult=false, reportDeprecated=false

from __future__ import annotations

import asyncio
import random
import zipfile
from datetime import datetime
from pathlib import Path

from crawl4ai import AsyncWebCrawler, CrawlerRunConfig

from pdd_crawler import config


async def _eval_js(crawler: AsyncWebCrawler, session_id: str, js_code: str) -> str:
    """Evaluate JavaScript on the current session page via the underlying Playwright page."""
    page, _ctx = await crawler.crawler_strategy.browser_manager.get_page(
        crawlerRunConfig=CrawlerRunConfig(session_id=session_id),
    )
    result = await page.evaluate(js_code)
    return str(result) if result else ""


async def _run_js_on_page(crawler: AsyncWebCrawler, session_id: str, js_code: str) -> None:
    """Execute JS on the current session page (fire-and-forget, no return value needed)."""
    page, _ctx = await crawler.crawler_strategy.browser_manager.get_page(
        crawlerRunConfig=CrawlerRunConfig(session_id=session_id),
    )
    await page.evaluate(js_code)


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


async def _get_current_url(crawler: AsyncWebCrawler, session_id: str) -> str:
    """Get current URL for a crawler session."""
    try:
        return await _eval_js(crawler, session_id, "window.location.href")
    except Exception:
        return ""


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
                text_content = await button.evaluate("el => (el.innerText || el.textContent || '').trim()")
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


def _build_click_js(selectors: list[str], texts: list[str]) -> str:
    joined_selectors = ",".join([f'"{s}"' for s in selectors])
    joined_texts = ",".join([f'"{t}"' for t in texts])
    return (
        "(() => {"
        f"const sels=[{joined_selectors}];"
        f"const texts=[{joined_texts}];"
        "for (const sel of sels) {"
        "  const el = document.querySelector(sel);"
        "  if (el && typeof el.click === 'function') {"
        "    el.scrollIntoView({block:'center'});"
        "    el.click();"
        "    return true;"
        "  }"
        "}"
        "const candidates = Array.from(document.querySelectorAll('button,a,span,div'));"
        "for (const el of candidates) {"
        "  const text = (el.innerText || el.textContent || '').trim();"
        "  if (!text) continue;"
        "  if (texts.some((t) => text.includes(t))) {"
        "    if (typeof el.click === 'function') {"
        "      el.scrollIntoView({block:'center'});"
        "      el.click();"
        "      return true;"
        "    }"
        "  }"
        "}"
        "return false;"
        "})()"
    )


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
    """Navigate to cashier bill tab using direct Playwright page navigation.

    Uses page.goto() directly instead of crawler.arun() for the cashier URL
    to avoid crawl4ai's scraping script injection, which is more easily
    detected by the cashier domain's anti-bot system.
    """
    # Step 1: Navigate to mms home via arun() to establish session context.
    result_1 = await crawler.arun(
        url=config.PDD_HOME_URL,
        config=CrawlerRunConfig(
            session_id=session_id,
            delay_before_return_html=2.0,
        ),
    )
    await _human_delay(1.5, 3.0)
    body_1 = _result_text(result_1)
    url_1 = await _get_current_url(crawler, session_id)
    if _is_blocked(body_1, url_1):
        _log_blocked_reason(body_1, url_1, "mms_home")
        return False

    # Step 2: Get the underlying Playwright page for direct navigation.
    page, _ctx = await crawler.crawler_strategy.browser_manager.get_page(
        crawlerRunConfig=CrawlerRunConfig(session_id=session_id),
    )

    # Strategy 1: Direct page.goto() — avoids crawl4ai script injection.
    try:
        await page.goto(tab_url, wait_until="domcontentloaded", timeout=30000)
        try:
            await page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass  # networkidle timeout is acceptable (long-polling, etc.)
        await _human_delay(2.0, 4.0)

        current_url = page.url
        body_text = await page.evaluate("document.body.innerText || ''") or ""
        if not _is_blocked(body_text, current_url):
            return True
        _log_blocked_reason(body_text, current_url, "strategy_1_page_goto")
    except Exception as e:
        print(f"[账单] Strategy 1 (page.goto) 异常: {e}")

    # Strategy 2: Go back to mms home, then JS redirect to cashier.
    try:
        await page.goto(
            config.PDD_HOME_URL, wait_until="networkidle", timeout=30000
        )
        await _human_delay(2.0, 3.5)

        await page.evaluate(f'window.location.href = "{tab_url}"')
        await asyncio.sleep(3.0)
        try:
            await page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        await _human_delay(2.0, 3.5)

        current_url = page.url
        body_text = await page.evaluate("document.body.innerText || ''") or ""
        if not _is_blocked(body_text, current_url):
            return True
        _log_blocked_reason(body_text, current_url, "strategy_2_js_redirect")
    except Exception as e:
        print(f"[账单] Strategy 2 (JS redirect) 异常: {e}")

    return False


async def export_single_bill(
    crawler: AsyncWebCrawler,
    session_id: str,
    tab_url: str,
    output_dir: Path,
) -> Path | None:
    """Export a single tab bill and return downloaded/extracted file path."""
    output_dir.mkdir(parents=True, exist_ok=True)

    ok = await _navigate_to_bill_tab(crawler, session_id, tab_url)
    if not ok:
        print(f"⚠️ 反爬机制触发，跳过: {tab_url}")
        return None

    # Get Playwright page for subsequent operations
    page, _ctx = await crawler.crawler_strategy.browser_manager.get_page(
        crawlerRunConfig=CrawlerRunConfig(session_id=session_id),
    )

    # 1) Click export button
    export_selectors = [
        'button[class*="export"]',
        '[class*="export"] button',
    ]
    click_js = _build_click_js(export_selectors, ["导出账单", "导出"])
    await _run_js_on_page(crawler, session_id, click_js)
    await asyncio.sleep(1.5)
    await _human_delay(1.5, 3.0)
    current_url = await _get_current_url(crawler, session_id)
    body_text = await _eval_js(crawler, session_id, "document.body.innerText || ''")
    if _is_blocked(body_text, current_url):
        print(f"⚠️ 页面被拦截，跳过: {tab_url}")
        return None

    # 2) Click confirm button in modal
    confirm_selectors = ['[class*="modal"] button[class*="primary"]']
    confirm_js = _build_click_js(confirm_selectors, ["确认导出", "确认", "确定"])
    await _run_js_on_page(crawler, session_id, confirm_js)
    await asyncio.sleep(1.5)
    await _human_delay(2.0, 4.0)
    current_url = await _get_current_url(crawler, session_id)
    body_text = await _eval_js(crawler, session_id, "document.body.innerText || ''")
    if _is_blocked(body_text, current_url):
        print(f"⚠️ 页面被拦截，跳过: {tab_url}")
        return None

    # Block check after triggering export
    await asyncio.sleep(1.0)
    current_url = await _get_current_url(crawler, session_id)
    body_text = await _eval_js(crawler, session_id, "document.body.innerText || ''")
    if _is_blocked(body_text, current_url):
        print(f"⚠️ 页面被拦截，跳过: {tab_url}")
        return None

    # 3) Go to export history — use page.goto() to avoid crawl4ai injection
    export_history_url = config.BILL_EXPORT_HISTORY_MAP.get(tab_url)
    if not export_history_url:
        tab_part = tab_url.split("tab=")[1].split("&")[0] if "tab=" in tab_url else "4001"
        export_history_url = (
            "https://cashier.pinduoduo.com/main/bills/export-history"
            f"?tab={tab_part}&__app_code=113"
        )

    try:
        await page.goto(export_history_url, wait_until="domcontentloaded", timeout=30000)
        try:
            await page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
    except Exception as e:
        print(f"⚠️ 导出记录页导航异常: {e}")
        return None
    await _human_delay(2.0, 4.0)
    current_url = page.url
    history_body = await page.evaluate("document.body.innerText || ''") or ""
    if _is_blocked(history_body, current_url):
        _log_blocked_reason(history_body, current_url, "export_history")
        print(f"⚠️ 导出记录页被拦截，跳过: {tab_url}")
        return None

    # 4) Click download and wait for file in downloads_path
    before_files = set(output_dir.iterdir()) if output_dir.exists() else set()
    download_selectors = [
        '[href*="download"]',
        'a[download]',
        'button[class*="download"]',
    ]
    download_js = _build_click_js(download_selectors, ["下载"])
    await _run_js_on_page(crawler, session_id, download_js)
    await asyncio.sleep(1.0)
    current_url = await _get_current_url(crawler, session_id)
    body_text = await _eval_js(crawler, session_id, "document.body.innerText || ''")
    if _is_blocked(body_text, current_url):
        print(f"⚠️ 下载步骤被拦截，跳过: {tab_url}")
        return None

    downloaded_file = await _wait_for_new_download(
        output_dir=output_dir,
        before=before_files,
        timeout_s=max(10, config.DOWNLOAD_TIMEOUT // 1000),
    )
    if downloaded_file is None:
        print("[账单] 下载超时")
        return None

    print(f"✅ 账单已下载: {downloaded_file}")
    if downloaded_file.suffix.lower() == ".zip":
        extracted = _extract_and_cleanup(downloaded_file)
        if extracted:
            print(f"✅ 已解压: {extracted}")
            return extracted
    return downloaded_file


async def export_all_bills(
    crawler: AsyncWebCrawler,
    session_id: str,
    cookie_path: Path,
    output_dir: Path,
) -> list[Path]:
    """Export bills from tab 4001 and 4002.

    Notes:
        - `crawler` should be created with `BrowserConfig(accept_downloads=True,
          downloads_path=str(output_dir), storage_state=str(cookie_path), ...)`
        - Uses a fresh session_id suffix per tab to avoid session contamination
          when one tab triggers anti-bot detection.
    """
    _ = cookie_path
    output_dir.mkdir(parents=True, exist_ok=True)

    downloaded: list[Path] = []
    for i, tab_url in enumerate([config.CASHIER_BILL_4001_URL, config.CASHIER_BILL_4002_URL]):
        # Use a unique session per tab to avoid contamination from blocked attempts
        tab_session_id = f"{session_id}_tab{i}"
        try:
            result = await export_single_bill(crawler, tab_session_id, tab_url, output_dir)
            if result is not None:
                downloaded.append(result)
        except Exception as e:
            print(f"⚠️ 导出失败: {e}")

    print(f"📊 共下载 {len(downloaded)} 个账单文件")
    return downloaded
