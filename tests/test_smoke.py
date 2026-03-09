"""Smoke tests for pdd_crawler package."""

import asyncio
import json
import subprocess
import tempfile
from pathlib import Path

import pytest
from playwright.async_api import async_playwright


def test_all_imports():
    """Test that all modules can be imported without error."""
    from pdd_crawler import config
    from pdd_crawler import cookie_manager
    from pdd_crawler import home_scraper
    from pdd_crawler import bill_exporter

    assert config is not None
    assert cookie_manager is not None
    assert home_scraper is not None
    assert bill_exporter is not None


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
    """Assert OUTPUT_BASE_DIR is a Path instance."""
    from pdd_crawler.config import OUTPUT_BASE_DIR, COOKIES_DIR

    assert isinstance(OUTPUT_BASE_DIR, Path)
    assert isinstance(COOKIES_DIR, Path)


def test_config_helpers():
    """Test config helper functions."""
    from pdd_crawler.config import get_cookie_path, get_shop_output_dir

    cookie_path = get_cookie_path("测试店铺")
    assert "测试店铺_cookies.json" in str(cookie_path)

    output_dir = get_shop_output_dir("测试店铺")
    assert "测试店铺" in str(output_dir)


def test_load_cookies_missing_file():
    """Test cookie_manager.load_cookies returns None for non-existent file."""
    from pdd_crawler.cookie_manager import load_cookies

    async def _async_test():
        async with async_playwright() as p:
            missing_path = Path("/tmp/nonexistent_path_xyz/cookies.json")
            result = await load_cookies(p, missing_path)
            assert result is None

    asyncio.run(_async_test())


def test_save_home_data():
    """Test home_scraper.save_home_data creates valid JSON file with correct content."""
    from pdd_crawler.home_scraper import save_home_data

    async def _async_test():
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            test_data = {
                "scraped_at": "2025-03-09T10:30:00",
                "url": "https://mms.pinduoduo.com/home/",
                "page_title": "Test Page",
                "shop_name": "测试店铺",
                "data": {
                    "item_0": "Test Item 1",
                    "item_1": "Test Item 2",
                },
            }

            result_path = await save_home_data(test_data, output_dir)

            assert result_path.exists()
            assert result_path.suffix == ".json"
            assert "home_data_" in result_path.name

            with open(result_path, "r", encoding="utf-8") as f:
                saved_data = json.load(f)

            assert saved_data["shop_name"] == "测试店铺"
            assert saved_data["data"]["item_0"] == "Test Item 1"

    asyncio.run(_async_test())


def test_cli_help():
    """Verify `python -m pdd_crawler --help` returns 0 and shows all options."""
    result = subprocess.run(
        ["python", "-m", "pdd_crawler", "--help"],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0

    help_text = result.stdout
    assert "--login" in help_text
    assert "--scrape-home" in help_text
    assert "--export-bills" in help_text
    assert "--all" in help_text
    assert "--shop-name" in help_text
