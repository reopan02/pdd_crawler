"""Home page scraper — extracts dashboard metrics from PDD home page."""

from __future__ import annotations

import asyncio
import json
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


async def scrape_home(page: Page) -> dict:
    """Navigate to PDD home and extract all visible dashboard metrics.

    Args:
        page: An authenticated Playwright page instance.

    Returns:
        A dict containing scraped_at, url, page_title, and data (key-value pairs).

    Raises:
        RuntimeError: If the page redirects to the login URL (session expired).
    """
    await page.goto(config.PDD_HOME_URL, timeout=config.PAGE_LOAD_TIMEOUT)
    await page.wait_for_load_state("networkidle")
    # Extra wait for SPA rendering to settle
    await asyncio.sleep(4)

    # Detect login redirect (session expired)
    current_url = page.url
    if "/login" in current_url:
        raise RuntimeError(f"会话已过期，页面跳转到登录页: {current_url}")

    page_title = await page.title()

    # Collect unique elements matching any data-related selector
    seen_texts: dict[str, str] = {}
    idx = 0
    for selector in _DATA_SELECTORS:
        elements = await page.query_selector_all(selector)
        for element in elements:
            text = (await element.inner_text()).strip()
            if not text:
                continue
            key = f"item_{idx}"
            # Deduplicate by text content
            if text not in seen_texts.values():
                seen_texts[key] = text
                idx += 1

    return {
        "scraped_at": datetime.now().isoformat(),
        "url": current_url,
        "page_title": page_title,
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


async def run_home_scraper(page: Page) -> Path:
    """Orchestrate home page scraping: scrape → save.

    Args:
        page: An authenticated Playwright page instance.

    Returns:
        The path of the saved JSON output file.
    """
    data = await scrape_home(page)
    return await save_home_data(data, config.OUTPUT_DIR)
