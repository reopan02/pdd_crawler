"""Smoke tests for pdd_crawler package."""

import asyncio
import json
import subprocess
import tempfile
from pathlib import Path

import pytest


def test_all_imports():
    """Test that all modules can be imported without error."""
    from pdd_crawler import config
    from pdd_crawler import cookie_manager
    from pdd_crawler import home_scraper
    from pdd_crawler import crawl4ai_bill_exporter

    assert config is not None
    assert cookie_manager is not None
    assert home_scraper is not None
    assert crawl4ai_bill_exporter is not None


def test_crawl4ai_importable():
    """Test that crawl4ai and its key classes can be imported."""
    import crawl4ai
    from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig

    assert crawl4ai is not None
    assert AsyncWebCrawler is not None
    assert BrowserConfig is not None
    assert CrawlerRunConfig is not None


def test_browser_config():
    """Test that get_browser_config() returns a BrowserConfig with stealth enabled."""
    from crawl4ai import BrowserConfig
    from pdd_crawler.cookie_manager import get_browser_config

    cfg = get_browser_config()
    assert isinstance(cfg, BrowserConfig)
    assert cfg.enable_stealth is True


def test_config_crawl4ai():
    """Test that config has BROWSER_CONFIG and BLOCKED_TEXTS for crawl4ai."""
    from pdd_crawler.config import BROWSER_CONFIG, BLOCKED_TEXTS

    assert isinstance(BROWSER_CONFIG, dict)
    assert "browser_type" in BROWSER_CONFIG
    assert "enable_stealth" in BROWSER_CONFIG
    assert BROWSER_CONFIG["enable_stealth"] is True

    assert isinstance(BLOCKED_TEXTS, list)
    assert len(BLOCKED_TEXTS) > 0


def test_config_urls():
    """Assert all URL constants contain correct domains and tab parameters."""
    from pdd_crawler.config import (
        PDD_HOME_URL,
        PDD_LOGIN_URL,
        CASHIER_BILL_4001_URL,
        CASHIER_BILL_4002_URL,
    )

    assert "mms.pinduoduo.com" in PDD_HOME_URL
    assert PDD_HOME_URL.startswith("https://")

    assert "mms.pinduoduo.com" in PDD_LOGIN_URL
    assert PDD_LOGIN_URL.startswith("https://")

    assert "cashier.pinduoduo.com" in CASHIER_BILL_4001_URL
    assert "tab=4001" in CASHIER_BILL_4001_URL
    assert CASHIER_BILL_4001_URL.startswith("https://")

    assert "cashier.pinduoduo.com" in CASHIER_BILL_4002_URL
    assert "tab=4002" in CASHIER_BILL_4002_URL
    assert CASHIER_BILL_4002_URL.startswith("https://")


def test_config_paths():
    """Assert COOKIES_DIR is a Path instance."""
    from pdd_crawler.config import COOKIES_DIR

    assert isinstance(COOKIES_DIR, Path)


def test_config_helpers():
    """Test config helper functions."""
    from pdd_crawler.config import get_cookie_path

    cookie_path = get_cookie_path("测试店铺")
    assert "测试店铺_cookies.json" in str(cookie_path)


def test_load_cookies_missing_file():
    """Test validate_cookies returns False for non-existent cookie file."""
    from pdd_crawler.cookie_manager import validate_cookies

    async def _async_test():
        missing_path = Path("/tmp/nonexistent_path_xyz/cookies.json")
        result = await validate_cookies(missing_path)
        assert result is False

    asyncio.run(_async_test())


def test_scrape_home_function_exists():
    """Test home_scraper.scrape_home is importable and async."""
    import inspect
    from pdd_crawler.home_scraper import scrape_home

    assert callable(scrape_home)
    assert inspect.iscoroutinefunction(scrape_home)


def test_cli_help():
    """Verify `python -m pdd_crawler --help` returns 0 and shows web options."""
    result = subprocess.run(
        ["python", "-m", "pdd_crawler", "--help"],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0

    help_text = result.stdout
    assert "--host" in help_text
    assert "--port" in help_text


def test_navigation_function_exists():
    """Verify _navigate_to_bill_tab has correct signature and new helpers exist."""
    import inspect
    from pdd_crawler.crawl4ai_bill_exporter import (
        _navigate_to_bill_tab,
        _take_debug_screenshot,
        _dismiss_popups,
    )

    # Check signature
    sig = inspect.signature(_navigate_to_bill_tab)
    params = list(sig.parameters.keys())
    assert params == ["crawler", "session_id", "tab_url"]
    assert sig.return_annotation is bool or "bool" in str(sig.return_annotation)

    # Check helpers are callable
    assert callable(_take_debug_screenshot)
    assert callable(_dismiss_popups)


def test_navigation_config():
    """Verify new navigation config constants."""
    from pdd_crawler.config import (
        SIDEBAR_TEXTS,
        NAV_MAX_RETRIES,
        NAV_RETRY_BASE_DELAY,
        DEBUG_SCREENSHOT_DIR,
    )

    assert isinstance(SIDEBAR_TEXTS, list)
    assert len(SIDEBAR_TEXTS) >= 2
    assert all(isinstance(t, str) for t in SIDEBAR_TEXTS)
    assert isinstance(NAV_MAX_RETRIES, int)
    assert NAV_MAX_RETRIES >= 1
    assert isinstance(NAV_RETRY_BASE_DELAY, (int, float))
    assert NAV_RETRY_BASE_DELAY > 0
    assert isinstance(DEBUG_SCREENSHOT_DIR, str)
