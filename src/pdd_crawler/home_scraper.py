"""Home page scraper — extracts dashboard metrics and shop name from PDD home page."""

# pyright: reportMissingImports=false, reportMissingTypeStubs=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportUnknownArgumentType=false, reportUnusedCallResult=false, reportDeprecated=false

from __future__ import annotations

import json
import re
from datetime import datetime

from crawl4ai import AsyncWebCrawler, CrawlerRunConfig

from pdd_crawler import config


async def _eval_js(crawler: AsyncWebCrawler, session_id: str, js_code: str) -> str:
    """Evaluate JavaScript on the current session page via the underlying Playwright page.

    crawl4ai's arun() rejects non-http URLs, so for JS-only operations on the
    current page we go through the browser_manager directly.
    """
    page, _ctx = await crawler.crawler_strategy.browser_manager.get_page(
        crawlerRunConfig=CrawlerRunConfig(session_id=session_id),
    )
    result = await page.evaluate(js_code)
    return str(result) if result else ""


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


# JavaScript to extract shop name by trying multiple selectors
_SHOP_NAME_JS = """
(function() {
    var selectors = [
        '[class*="shopName"]',
        '[class*="shop-name"]',
        '[class*="ShopName"]',
        '[class*="mallName"]',
        '[class*="mall-name"]',
        '[class*="storeName"]',
        '[class*="store-name"]',
        'header [class*="name"]',
        '[class*="header"] [class*="name"]',
        '[class*="user"] [class*="name"]',
        '[class*="merchant"] [class*="name"]'
    ];
    for (var i = 0; i < selectors.length; i++) {
        try {
            var el = document.querySelector(selectors[i]);
            if (el) {
                var text = (el.textContent || '').trim();
                if (text.length > 1 && text.length < 100) {
                    return text;
                }
            }
        } catch(e) {}
    }
    // Fallback: try page title
    var title = document.title || '';
    if (title.indexOf(' - ') !== -1) {
        var name = title.split(' - ')[0].trim();
        if (name && name !== '拼多多商家后台') {
            return name;
        }
    }
    return '';
})();
"""

# JavaScript to extract dashboard data using _DATA_SELECTORS
_EXTRACT_DATA_JS = """
(function() {
    var selectors = %s;
    var seenTexts = {};
    var idx = 0;
    var seenValues = {};
    for (var s = 0; s < selectors.length; s++) {
        try {
            var elements = document.querySelectorAll(selectors[s]);
            for (var e = 0; e < elements.length; e++) {
                try {
                    var text = (elements[e].textContent || '').trim();
                    if (!text) continue;
                    if (seenValues[text]) continue;
                    seenValues[text] = true;
                    seenTexts['item_' + idx] = text;
                    idx++;
                } catch(ex) {}
            }
        } catch(ex) {}
    }
    if (idx === 0) {
        try {
            var body = document.body.innerText || '';
            seenTexts['full_page_text'] = body.trim();
        } catch(ex) {
            seenTexts['error'] = '无法提取页面内容';
        }
    }
    return JSON.stringify(seenTexts);
})();
""" % json.dumps(_DATA_SELECTORS)


async def get_shop_name(crawler: AsyncWebCrawler, session_id: str) -> str:
    """Extract shop name from PDD home page.

    Tries multiple selectors to find the shop name display.
    Falls back to a timestamp-based name if not found.

    Args:
        crawler: An active crawl4ai crawler instance.
        session_id: Session identifier for the crawler.

    Returns:
        Sanitized shop name string.
    """
    try:
        text = await _eval_js(crawler, session_id, _SHOP_NAME_JS)
        text = text.strip().strip('"').strip("'")
        if text and len(text) > 1 and len(text) < 100:
            print(f"[首页] 找到店铺名称: {text}")
            return _sanitize_name(text)
    except Exception:
        pass

    # Fallback: try getting page title via JS
    try:
        title = await _eval_js(crawler, session_id, "document.title")
        title = title.strip().strip('"').strip("'")
        if title and " - " in title:
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


async def scrape_home(crawler: AsyncWebCrawler, session_id: str) -> dict[str, object]:
    """Navigate to PDD home and extract all visible dashboard metrics.

    Args:
        crawler: An active crawl4ai crawler instance.
        session_id: Session identifier for the crawler.

    Returns:
        A dict containing scraped_at, url, page_title, shop_name, and data.

    Raises:
        RuntimeError: If the page redirects to the login URL (session expired).
    """
    # Navigate to home page
    result = await crawler.arun(
        url=config.PDD_HOME_URL,
        config=CrawlerRunConfig(
            session_id=session_id,
            wait_for="body",
        ),
    )

    # Check current URL for login redirect
    current_url = await _eval_js(crawler, session_id, "window.location.href")
    current_url = current_url.strip().strip('"').strip("'")
    if not current_url:
        current_url = getattr(result, "url", config.PDD_HOME_URL)

    if "/login" in current_url:
        raise RuntimeError(f"会话已过期，页面跳转到登录页: {current_url}")

    # Get page title
    page_title = await _eval_js(crawler, session_id, "document.title")
    page_title = page_title.strip().strip('"').strip("'")

    # Get shop name
    shop_name = await get_shop_name(crawler, session_id)

    # Extract dashboard data via JS
    data_raw = await _eval_js(crawler, session_id, _EXTRACT_DATA_JS)
    seen_texts: dict[str, str] = {}
    if data_raw.strip():
        try:
            seen_texts = json.loads(data_raw.strip())
        except (json.JSONDecodeError, ValueError):
            pass

    # Fallback if nothing extracted
    if not seen_texts:
        body_text = await _eval_js(crawler, session_id, "document.body.innerText || ''")
        if body_text.strip():
            seen_texts["full_page_text"] = body_text.strip()
        else:
            seen_texts["error"] = "无法提取页面内容"

    return {
        "scraped_at": datetime.now().isoformat(),
        "url": current_url,
        "page_title": page_title,
        "shop_name": shop_name,
        "data": seen_texts,
    }
