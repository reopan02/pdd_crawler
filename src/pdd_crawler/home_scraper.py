"""Home page scraper — extracts dashboard metrics and shop name from PDD home page."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from playwright.async_api import Page

from pdd_crawler import config


# CSS selectors that commonly hold dashboard data on PDD
_DATA_SELECTORS = [
    '[class*="data"]',
    '[class*="card"]',
    '[class*="metric"]',
    '[class*="stat"]',
    '[class*="overview"]',
    '[class*="summary"]',
]


def _sanitize_name(name: str) -> str:
    """Sanitize shop name for use as directory/filename.

    Removes/replaces characters that are invalid in file paths.
    """
    # Remove or replace invalid characters
    name = re.sub(r'[<>:"/\\|?*]', "_", name)
    # Remove leading/trailing spaces and dots
    name = name.strip().strip(".")
    # Limit length
    if len(name) > 100:
        name = name[:100]
    # Fallback if empty
    if not name:
        name = "pdd_shop"
    return name


async def get_shop_name(page: Page) -> str:
    """Extract shop name from PDD home page.

    Tries multiple selectors to find the shop name display.
    Falls back to a timestamp-based name if not found.
    """
    # Wait a bit for the page to fully render
    await page.wait_for_timeout(2000)

    # Try various selectors for shop name
    shop_name_selectors = [
        # Common shop name class patterns
        '[class*="shopName"]',
        '[class*="shop-name"]',
        '[class*="ShopName"]',
        '[class*="mallName"]',
        '[class*="mall-name"]',
        '[class*="storeName"]',
        '[class*="store-name"]',
        # Header/brand area
        'header [class*="name"]',
        '[class*="header"] [class*="name"]',
        # Try finding text that looks like a shop name
        '[class*="user"] [class*="name"]',
        '[class*="merchant"] [class*="name"]',
    ]

    for selector in shop_name_selectors:
        try:
            element = page.locator(selector).first
            if await element.is_visible(timeout=2000):
                text = (await element.text_content() or "").strip()
                if text and len(text) > 1 and len(text) < 100:
                    print(f"[首页] 找到店铺名称: {text}")
                    return _sanitize_name(text)
        except Exception:
            continue

    # Try to get from page title
    try:
        title = await page.title()
        # PDD titles often contain shop name: "店铺名称 - 拼多多商家后台"
        if " - " in title:
            name = title.split(" - ")[0].strip()
            if name and name != "拼多多商家后台":
                print(f"[首页] 从标题提取店铺名称: {name}")
                return _sanitize_name(name)
    except Exception:
        pass

    # Fallback: use timestamp
    fallback_name = f"shop_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    print(f"[首页] 未找到店铺名称，使用默认: {fallback_name}")
    return fallback_name


async def scrape_home(page: Page) -> dict:
    """Navigate to PDD home and extract all visible dashboard metrics.

    Args:
        page: An authenticated Playwright page instance.

    Returns:
        A dict containing scraped_at, url, page_title, shop_name, and data.

    Raises:
        RuntimeError: If the page redirects to the login URL (session expired).
    """
    await page.goto(
        config.PDD_HOME_URL,
        wait_until="domcontentloaded",
        timeout=config.PAGE_LOAD_TIMEOUT,
    )
    await page.wait_for_timeout(8000)

    current_url = page.url
    if "/login" in current_url:
        raise RuntimeError(f"会话已过期，页面跳转到登录页: {current_url}")

    page_title = await page.title()
    shop_name = await get_shop_name(page)

    # Collect unique elements matching any data-related selector
    seen_texts: dict[str, str] = {}
    idx = 0
    for selector in _DATA_SELECTORS:
        elements = await page.query_selector_all(selector)
        for element in elements:
            try:
                text = (await element.text_content() or "").strip()
            except Exception:
                continue
            if not text:
                continue
            key = f"item_{idx}"
            if text not in seen_texts.values():
                seen_texts[key] = text
                idx += 1

    # Fallback: if selector-based extraction found nothing
    if not seen_texts:
        try:
            body_text = await page.inner_text("body")
            seen_texts["full_page_text"] = body_text.strip()
        except Exception:
            seen_texts["error"] = "无法提取页面内容"

    return {
        "scraped_at": datetime.now().isoformat(),
        "url": current_url,
        "page_title": page_title,
        "shop_name": shop_name,
        "data": seen_texts,
    }


async def save_home_data(data: dict, output_dir: Path) -> Path:
    """Persist scraped home data as pretty-printed JSON.

    Args:
        data: The dict returned by :func:`scrape_home`.
        output_dir: Directory where the JSON file will be saved.

    Returns:
        The path of the saved JSON file.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = output_dir / f"home_data_{timestamp}.json"

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"首页数据已保存: {filepath}")
    return filepath


async def run_home_scraper(
    page: Page, output_dir: Path | None = None
) -> tuple[str, Path]:
    """Orchestrate home page scraping: scrape → save.

    Args:
        page: An authenticated Playwright page instance.
        output_dir: Directory to save output. If None, uses shop_name-based dir.

    Returns:
        Tuple of (shop_name, output_file_path).
    """
    data = await scrape_home(page)
    shop_name = data.get("shop_name", "pdd_shop")

    if output_dir is None:
        output_dir = config.OUTPUT_BASE_DIR / shop_name

    filepath = await save_home_data(data, output_dir)
    return shop_name, filepath
