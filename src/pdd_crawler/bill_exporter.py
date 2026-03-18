"""Bill exporter — exports cashier bills via Playwright Page (CDP).

Exports cashier bills for tab 4001/4002, downloads files to the configured
downloads directory, and auto-extracts ZIP files.

All functions accept a Playwright Page object directly (no crawl4ai).
"""

from __future__ import annotations

import asyncio
import random
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path

import aiohttp
from playwright.async_api import Page

import re

from pdd_crawler import config


async def _download_file_direct(
    url: str,
    cookies: list[dict],
    output_path: Path,
) -> bool:
    """Download file directly using aiohttp with cookies from Playwright.
    
    This is a workaround for Playwright's download.save_as() returning 0 bytes
    in Docker Chrome environments.
    """
    try:
        # Build cookie dict for aiohttp
        cookie_dict = {c["name"]: c["value"] for c in cookies}
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://cashier.pinduoduo.com/",
        }
        
        async with aiohttp.ClientSession(cookies=cookie_dict, headers=headers) as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                if resp.status != 200:
                    print(f"[账单] 直接下载失败，HTTP状态码: {resp.status}")
                    return False
                
                data = await resp.read()
                if len(data) == 0:
                    print("[账单] 直接下载返回空内容")
                    return False
                
                output_path.write_bytes(data)
                print(f"[账单] 直接下载成功: {output_path} ({len(data)} bytes)")
                return True
                
    except Exception as e:
        print(f"[账单] 直接下载失败: {e}")
        return False


def _is_valid_zip(zip_path: Path) -> bool:
    """Check if file is a valid ZIP file by checking magic bytes."""
    if not zip_path.exists() or zip_path.stat().st_size < 4:
        return False
    try:
        with open(zip_path, "rb") as f:
            magic = f.read(4)
        # ZIP files start with PK\x03\x04 or PK\x05\x06 or PK\x07\x08
        return magic.startswith(b"PK")
    except Exception:
        return False


def _read_file_head(zip_path: Path, max_bytes: int = 500) -> str:
    """Read beginning of file for debugging (to detect HTML error pages)."""
    try:
        with open(zip_path, "rb") as f:
            data = f.read(max_bytes)
        # Try UTF-8 first, then latin-1
        for encoding in ("utf-8", "latin-1", "gbk"):
            try:
                return data.decode(encoding, errors="replace")
            except Exception:
                continue
        return data.hex()[:100]
    except Exception as e:
        return f"<无法读取: {e}>"


def _extract_and_cleanup(zip_path: Path) -> Path | None:
    """Extract zip file to same directory, delete zip, return first extracted file."""
    if not zip_path.exists():
        return None

    # Validate ZIP format before attempting extraction
    if not _is_valid_zip(zip_path):
        file_head = _read_file_head(zip_path)
        print(f"[账单] ⚠️ 文件不是有效的ZIP格式: {zip_path.name}")
        print(f"[账单] 文件头内容: {file_head[:200]}...")
        # Check if it's an HTML error page
        if "<html" in file_head.lower() or "<!doctype" in file_head.lower():
            print(f"[账单] ❌ 下载的是HTML页面而非ZIP文件，可能是登录过期或风控拦截")
        # Clean up invalid file
        try:
            zip_path.unlink()
            print(f"[账单] 已删除无效文件: {zip_path.name}")
        except Exception:
            pass
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
        # Clean up corrupted file
        try:
            zip_path.unlink()
        except Exception:
            pass

    return None


def _is_blocked(body: str, url: str) -> bool:
    """Return True if anti-crawl/session-expired content is detected."""
    if "login" in url.lower():
        return True
    matched = [t for t in config.BLOCKED_TEXTS if t in body]
    if not matched:
        return False
    if len(body.strip()) < 1000:
        return True
    if len(matched) >= 2:
        return True
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
    page: Page, step_name: str, output_dir: Path | None = None
) -> Path | None:
    """Take a debug screenshot and save it to the output directory."""
    try:
        if output_dir is None:
            debug_dir = config.PROJECT_ROOT / "output" / "debug"
        else:
            debug_dir = output_dir / "debug"

        debug_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        screenshot_path = debug_dir / f"nav_{step_name}_{timestamp}.png"
        await page.screenshot(path=screenshot_path)
        return screenshot_path
    except Exception as e:
        print(f"[账单-导航] 调试截图失败: {e}")
        return None


async def _dismiss_popups(page: Page) -> None:
    """Dismiss common PDD popups/modals by clicking close buttons."""
    try:
        close_selectors = [
            '[class*="modal"] [class*="close"]',
            '[class*="dialog"] [class*="close"]',
            '[class*="overlay"] [class*="close"]',
            ".ant-modal-close",
        ]
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
    except Exception:
        pass


async def _read_picker_date(page: Page) -> str:
    """Read the current date string from the date range input on the page."""
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
    """Extract a YYYY-MM-DD date from the picker input value."""
    m = re.search(r"(\d{4}-\d{2}-\d{2})", picker_value)
    return m.group(1) if m else ""


async def _select_yesterday_date(
    page: Page, reference_today: date | None = None
) -> str:
    """Select yesterday's date range in the cashier bill date picker."""
    try:
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

            confirm_btn = page.locator("button:has-text('确认')")
            if await confirm_btn.count() > 0:
                try:
                    await confirm_btn.first.click(timeout=2000)
                    await _human_delay(0.3, 0.6)
                except Exception:
                    pass
        else:
            # 4002 mode: JS injection
            print("[账单-日期] 无'昨天'按钮, 使用JS注入模式 (4002模式)")
            await page.keyboard.press("Escape")
            await _human_delay(0.3, 0.6)

            yesterday_str = pdd_yesterday.isoformat()
            target_value = f"{yesterday_str} 00:00:00 ~ {yesterday_str} 23:59:59"

            input_sel = '[data-testid="beast-core-rangePicker-htmlInput"]'
            input_loc = page.locator(input_sel)
            if await input_loc.count() == 0:
                for ph in ("开始日期-结束日期", "请选择时间范围"):
                    input_loc = page.get_by_placeholder(ph)
                    if await input_loc.count() > 0:
                        break

            if await input_loc.count() == 0:
                print("[账单-日期] 4002模式: 未找到日期输入框")
                return ""

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

        # 4) Read back the actual selected date
        final_value = await _read_picker_date(page)
        selected_date = _parse_date_from_picker_value(final_value)
        if selected_date:
            print(f"[账单-日期] 最终选中日期: {selected_date}")
        else:
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
    """Click element using Playwright native API."""
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
    page: Page,
    tab_url: str,
) -> bool:
    """Navigate to cashier bill tab via MMS SSO proxy.

    Flow:
      1. Navigate to mms.pinduoduo.com/cashier/finance/payment-bills
      2. MMS generates auth ticket → redirects to cashier.pinduoduo.com/main/auth?ticket=...
      3. cashier validates ticket and sets session cookies
      4. Navigate to the specific bill tab URL
    """
    for attempt in range(1, config.NAV_MAX_RETRIES + 1):
        try:
            # ── Step 1: SSO via MMS proxy ──
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

    await _take_debug_screenshot(page, "bill_all_retries_failed", None)
    print(f"[账单-导航] ❌ 导航失败，已重试{config.NAV_MAX_RETRIES}次")
    return False


async def export_single_bill(
    page: Page,
    tab_url: str,
    output_dir: Path,
    reference_today: date | None = None,
) -> tuple[Path | None, date | None]:
    """Export a single tab bill and return downloaded/extracted file path.

    Flow:
    1. Navigate to bill tab via SSO proxy
    2. Select yesterday's date range
    3. Click export button
    4. Navigate to export-history page, poll for download button
    5. Click download, wait for file, extract if ZIP
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    ok = await _navigate_to_bill_tab(page, tab_url)
    if not ok:
        print(f"⚠️ 反爬机制触发，跳过: {tab_url}")
        return None, None

    # 0) Select yesterday's date range
    selected_date = await _select_yesterday_date(page, reference_today)
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

    # 1) Click export button
    export_selectors = [
        "#exportBalance-btn",
        'button[class*="export"]',
        '[class*="export"] button',
    ]

    clicked = await _pw_click(page, export_selectors, ["导出账单", "导出"])
    if not clicked:
        print("[账单] 未找到导出按钮")
        return None, resolved_today
    print("[账单] 已点击导出按钮，等待服务端生成导出任务...")
    await _human_delay(2.0, 4.0)

    # 2) Navigate to export-history page
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
        await page.goto(
            export_history_url, wait_until="domcontentloaded", timeout=30000
        )
    except Exception as e:
        print(f"[账单] 导航到导出历史页失败: {e}")
        return None, resolved_today

    await _human_delay(2.0, 3.0)
    try:
        await page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass

    current_url = page.url or ""
    print(f"[账单] 已到达导出历史页: {current_url}")

    history_body = await page.evaluate("document.body.innerText || ''") or ""
    if _is_blocked(history_body, current_url):
        _log_blocked_reason(history_body, current_url, "export_history")
        print(f"⚠️ 导出记录页被拦截，跳过: {tab_url}")
        return None, resolved_today

    await _take_debug_screenshot(page, "export_history_page", output_dir)

    # 3) Poll for download button
    print("[账单] 寻找下载按钮...")

    download_selectors = [
        "#downloadBalance-btn-0",
        "[id^='downloadBalance-btn']",
        'button:has-text("下载账单")',
        'button:has-text("下载")',
        '[href*="download"]',
        "a[download]",
        'button[class*="download"]',
    ]

    max_poll_attempts = 4
    poll_interval = 5.0
    clicked_download = False

    for poll_idx in range(max_poll_attempts):
        clicked_download = await _pw_click(
            page, download_selectors, ["下载账单", "下载"]
        )
        if clicked_download:
            break

        if poll_idx < max_poll_attempts - 1:
            print(
                f"[账单] 下载按钮未就绪, "
                f"{poll_interval:.0f}s后刷新重试 ({poll_idx + 1}/{max_poll_attempts})..."
            )
            await asyncio.sleep(poll_interval)
            try:
                await page.reload(wait_until="domcontentloaded", timeout=30000)
            except Exception:
                pass
            await _human_delay(1.0, 2.0)
            try:
                await page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass

    if not clicked_download:
        print("[账单] 下载按钮未找到，导出任务可能仍在生成中")
        await _take_debug_screenshot(page, "download_btn_not_found", output_dir)
        return None, resolved_today

    print("[账单] 已点击下载按钮，等待下载完成...")

    # 4) Wait for download
    before_files = set(output_dir.iterdir()) if output_dir.exists() else set()

    downloaded_file = await _wait_for_new_download(
        output_dir=output_dir,
        before=before_files,
        timeout_s=max(10, config.DOWNLOAD_TIMEOUT // 1000),
    )

    if downloaded_file is None:
        print("[账单] 轮询未检测到文件，尝试expect_download方式...")
        try:
            async with page.expect_download(timeout=60000) as download_info:
                await _pw_click(page, download_selectors, ["下载账单", "下载"])
            download = await download_info.value
            suggested_name = download.suggested_filename
            download_url = download.url
            print(f"[账单] 下载文件名: {suggested_name}")
            print(f"[账单] 下载URL: {download_url[:100]}...")
            
            download_path = output_dir / suggested_name
            
            # Workaround: Playwright's download.save_as() returns 0 bytes in Docker Chrome
            # Use direct HTTP download with cookies instead
            print("[账单] 使用直接HTTP下载方式...")
            cookies = await page.context.cookies()
            download_success = await _download_file_direct(
                url=download_url,
                cookies=cookies,
                output_path=download_path,
            )
            
            if not download_success:
                # Fallback to Playwright's save_as (might work in non-Docker environments)
                print("[账单] 直接下载失败，尝试Playwright save_as...")
                await download.save_as(download_path)
            
            downloaded_file = download_path
        except Exception as e:
            print(f"[账单] 下载失败: {e}")
            return None, resolved_today

    # Validate downloaded file
    if not downloaded_file.exists():
        print(f"[账单] ❌ 下载文件不存在: {downloaded_file}")
        return None, resolved_today

    file_size = downloaded_file.stat().st_size
    print(f"✅ 账单已下载: {downloaded_file} ({file_size} bytes)")

    # Check if file is suspiciously small (likely an error page)
    if file_size < 100:
        print(f"[账单] ⚠️ 文件过小({file_size} bytes)，可能不是有效账单文件")
        file_head = _read_file_head(downloaded_file, 200)
        print(f"[账单] 文件内容: {file_head}")
        try:
            downloaded_file.unlink()
        except Exception:
            pass
        return None, resolved_today

    if downloaded_file.suffix.lower() == ".zip":
        # Validate it's actually a ZIP before extracting
        if not _is_valid_zip(downloaded_file):
            print(f"[账单] ❌ 下载的文件不是有效的ZIP格式")
            # Try to diagnose what it is
            file_head = _read_file_head(downloaded_file)
            print(f"[账单] 文件头: {file_head[:300]}...")
            if "<html" in file_head.lower() or "<!doctype" in file_head.lower():
                print(f"[账单] ❌ 下载的是HTML页面，可能是登录过期或需要验证码")
            # Clean up and return None
            try:
                downloaded_file.unlink()
            except Exception:
                pass
            return None, resolved_today

        extracted = _extract_and_cleanup(downloaded_file)
        if extracted:
            print(f"✅ 已解压: {extracted}")
            return extracted, resolved_today
        # Extraction failed, return None
        return None, resolved_today

    return downloaded_file, resolved_today


async def export_all_bills(
    page: Page,
    output_dir: Path,
) -> list[Path]:
    """Export bills from tab 4001 and 4002.

    4001 is exported first; its resolved "today" date is passed to 4002.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    downloaded: list[Path] = []
    reference_today: date | None = None

    for tab_url in [config.CASHIER_BILL_4001_URL, config.CASHIER_BILL_4002_URL]:
        try:
            file_path, resolved_today = await export_single_bill(
                page, tab_url, output_dir, reference_today
            )
            if file_path is not None:
                downloaded.append(file_path)
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
