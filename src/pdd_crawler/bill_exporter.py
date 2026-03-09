"""Bill exporter for downloading cashier bills from PDD.

Supports:
- Navigating through mms sidebar to avoid anti-crawl
- Downloading bills from export-history page
- Extracting zip files and deleting them after extraction
"""

from datetime import datetime
from pathlib import Path
from typing import Optional
import random
import zipfile
import shutil

from playwright.async_api import BrowserContext, Page

from pdd_crawler import config


def _is_blocked(body: str, url: str) -> bool:
    """Return True if the page shows anti-crawl / session-expired content."""
    blocked_texts = ["登录异常", "关闭页面后重试", "访问异常", "验证身份"]
    return any(t in body for t in blocked_texts) or "login" in url.lower()


def _extract_and_cleanup(zip_path: Path) -> Optional[Path]:
    """Extract zip file to same directory, delete zip, return first extracted file.

    Returns the path to the first extracted file (usually CSV), or None on failure.
    """
    if not zip_path.exists():
        return None

    extract_dir = zip_path.parent

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            extracted_files = zf.namelist()
            zf.extractall(extract_dir)

        # Delete the zip file
        zip_path.unlink()
        print(f"[账单] 已解压并删除压缩包: {zip_path.name}")

        # Return the first extracted file (usually CSV)
        if extracted_files:
            return extract_dir / extracted_files[0]

    except Exception as e:
        print(f"[账单] 解压失败: {e}")
        return None

    return None


async def _navigate_to_bill_tab(
    context: BrowserContext, page: Page, tab_url: str
) -> Page:
    """Navigate to a specific cashier bill tab using multiple strategies."""
    # Ensure we start from mms home
    if "mms.pinduoduo.com" not in page.url or "/login" in page.url:
        await page.goto(
            config.PDD_HOME_URL,
            wait_until="domcontentloaded",
            timeout=config.PAGE_LOAD_TIMEOUT,
        )
        await page.wait_for_timeout(random.randint(4000, 6000))

    # Strategy 1: Try clicking through sidebar
    sidebar_selectors = [
        'text="账房"',
        'text="资金管理"',
        'a[href*="cashier"]',
    ]

    for selector in sidebar_selectors:
        try:
            link = page.locator(selector).first
            if await link.is_visible(timeout=2000):
                print(f"[账单] 找到侧边栏入口: {selector}")
                await link.click()
                await page.wait_for_timeout(3000)
                break
        except Exception:
            continue

    # Check if sidebar opened a new tab
    for p in context.pages:
        if p is not page and "cashier" in p.url:
            body = await p.text_content("body") or ""
            if not _is_blocked(body, p.url):
                print("[账单] 侧边栏打开了新标签页，跳转到具体账单页...")
                await p.evaluate(f'location.href = "{tab_url}"')
                await p.wait_for_timeout(random.randint(5000, 8000))
                return p

    # Strategy 2: JS navigation from current page
    if "cashier" in page.url:
        await page.evaluate(f'location.href = "{tab_url}"')
    else:
        await page.evaluate(f'location.href = "{tab_url}"')

    await page.wait_for_timeout(random.randint(5000, 8000))
    return page


async def export_single_bill(
    context: BrowserContext,
    opener_page: Page,
    tab_url: str,
    output_dir: Path,
) -> Optional[Path]:
    """Export and download a single bill.

    Args:
        context: BrowserContext.
        opener_page: Page on mms.pinduoduo.com.
        tab_url: Cashier bill tab URL.
        output_dir: Directory to save files (shop-specific).

    Returns:
        Path to the final file (extracted CSV), or None if failed.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    bill_page = await _navigate_to_bill_tab(context, opener_page, tab_url)
    is_separate_page = bill_page is not opener_page

    try:
        # Check if blocked
        body = await bill_page.text_content("body") or ""
        if _is_blocked(body, bill_page.url):
            print(f"⚠️ 反爬机制触发，跳过: {tab_url}")
            return None

        # Find "导出账单" button
        button = None
        selectors = [
            lambda: bill_page.get_by_text("导出账单"),
            lambda: bill_page.get_by_role("button", name="导出账单"),
            lambda: bill_page.locator('button:has-text("导出")'),
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

        # Handle confirmation modal
        modal_selectors = [
            'button:has-text("确认导出")',
            'button:has-text("确认")',
            'button:has-text("确定")',
            '[class*="modal"] button[class*="primary"]',
        ]

        for selector in modal_selectors:
            try:
                btn = bill_page.locator(selector).first
                if await btn.is_visible(timeout=2000):
                    print(f"[账单] 点击确认按钮: {selector}")
                    await btn.click()
                    await bill_page.wait_for_timeout(3000)
                    break
            except Exception:
                continue

        # Navigate to export-history
        export_history_url = config.BILL_EXPORT_HISTORY_MAP.get(tab_url)
        if not export_history_url:
            tab_part = (
                tab_url.split("tab=")[1].split("&")[0] if "tab=" in tab_url else "4001"
            )
            export_history_url = (
                f"https://cashier.pinduoduo.com/main/bills/export-history"
                f"?tab={tab_part}&__app_code=113"
            )

        print(f"[账单] 跳转到导出记录页...")
        await bill_page.evaluate(f'location.href = "{export_history_url}"')
        await bill_page.wait_for_timeout(8000)

        # Find and click download button
        download_selectors = [
            'a:has-text("下载")',
            'button:has-text("下载")',
            'text="下载"',
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
                        suggested = f"bill_{tab_part}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

                    # Save the file
                    download_path = output_dir / suggested
                    await download.save_as(str(download_path))
                    print(f"✅ 账单已下载: {download_path}")

                    # Extract if it's a zip file
                    if download_path.suffix.lower() == ".zip":
                        extracted = _extract_and_cleanup(download_path)
                        if extracted:
                            print(f"✅ 已解压: {extracted}")
                            return extracted
                        return download_path

                    return download_path

            except Exception as e:
                print(f"[账单] 下载尝试失败: {e}")
                continue

        print(f"⚠️ 未能在导出记录页找到下载按钮")
        return None

    finally:
        if is_separate_page:
            await bill_page.close()


async def export_all_bills(
    context: BrowserContext, page: Page, output_dir: Path
) -> list[Path]:
    """Download bills from all cashier tabs.

    Args:
        context: BrowserContext.
        page: Page on mms.pinduoduo.com.
        output_dir: Shop-specific output directory.

    Returns:
        List of paths to downloaded/extracted files.
    """
    downloaded: list[Path] = []

    for url in [config.CASHIER_BILL_4001_URL, config.CASHIER_BILL_4002_URL]:
        try:
            result = await export_single_bill(context, page, url, output_dir)
            if result is not None:
                downloaded.append(result)
        except Exception as e:
            print(f"⚠️ 导出失败: {e}")

        # Navigate back to mms between exports
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
