"""Home page scraper — extracts dashboard metrics and shop name from PDD home page.

All functions accept a Playwright Page object directly (no crawl4ai dependency).
"""

from __future__ import annotations

import json
import re
from datetime import datetime

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
    """Sanitize shop name for use as directory/filename."""
    name = re.sub(r'[<>:"/\\|?*]', "_", name)
    name = name.strip().strip(".")
    if len(name) > 100:
        name = name[:100]
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

# JavaScript to extract dashboard data
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


async def get_shop_name(page: Page) -> str:
    """Extract shop name from PDD home page.

    Args:
        page: Playwright Page already on MMS home.

    Returns:
        Sanitized shop name string.
    """
    try:
        text = await page.evaluate(_SHOP_NAME_JS)
        if isinstance(text, str):
            text = text.strip().strip('"').strip("'")
            if text and 1 < len(text) < 100:
                print(f"[首页] 找到店铺名称: {text}")
                return _sanitize_name(text)
    except Exception:
        pass

    # Fallback: page title
    try:
        title = await page.title()
        if title and " - " in title:
            name = title.split(" - ")[0].strip()
            if name and name != "拼多多商家后台":
                print(f"[首页] 从标题提取店铺名称: {name}")
                return _sanitize_name(name)
    except Exception:
        pass

    fallback_name = f"shop_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    print(f"[首页] 未找到店铺名称，使用默认: {fallback_name}")
    return fallback_name


async def scrape_home(page: Page) -> dict[str, object]:
    """Navigate to PDD home and extract all visible dashboard metrics.

    Args:
        page: Playwright Page connected via CDP.

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
    # Wait for content to render
    try:
        await page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass

    current_url = page.url or ""
    if "/login" in current_url:
        raise RuntimeError(f"会话已过期，页面跳转到登录页: {current_url}")

    page_title = await page.title()
    shop_name = await get_shop_name(page)

    # Extract dashboard data via JS
    data_raw = await page.evaluate(_EXTRACT_DATA_JS)
    seen_texts: dict[str, str] = {}
    if isinstance(data_raw, str) and data_raw.strip():
        try:
            seen_texts = json.loads(data_raw.strip())
        except (json.JSONDecodeError, ValueError):
            pass

    if not seen_texts:
        body_text = await page.evaluate("document.body.innerText || ''")
        if isinstance(body_text, str) and body_text.strip():
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
