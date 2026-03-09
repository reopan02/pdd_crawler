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
    # Import all modules
    from pdd_crawler import config
    from pdd_crawler import cookie_manager
    from pdd_crawler import home_scraper
    from pdd_crawler import bill_exporter

    # Verify modules are accessible
    assert config is not None
    assert cookie_manager is not None
    assert home_scraper is not None
    assert bill_exporter is not None


def test_config_urls():
    """Assert all 4 URL constants contain correct domains and tab parameters."""
    from pdd_crawler.config import (
        PDD_HOME_URL,
        PDD_LOGIN_URL,
        CASHIER_BILL_4001_URL,
        CASHIER_BILL_4002_URL,
    )

    # PDD_HOME_URL should contain pinduoduo domain
    assert "mms.pinduoduo.com" in PDD_HOME_URL
    assert PDD_HOME_URL.startswith("https://")

    # PDD_LOGIN_URL should contain pinduoduo domain
    assert "mms.pinduoduo.com" in PDD_LOGIN_URL
    assert PDD_LOGIN_URL.startswith("https://")

    # CASHIER_BILL_4001_URL should contain cashier domain and tab=4001
    assert "cashier.pinduoduo.com" in CASHIER_BILL_4001_URL
    assert "tab=4001" in CASHIER_BILL_4001_URL
    assert CASHIER_BILL_4001_URL.startswith("https://")

    # CASHIER_BILL_4002_URL should contain cashier domain and tab=4002
    assert "cashier.pinduoduo.com" in CASHIER_BILL_4002_URL
    assert "tab=4002" in CASHIER_BILL_4002_URL
    assert CASHIER_BILL_4002_URL.startswith("https://")


def test_config_paths():
    """Assert COOKIE_PATH, DOWNLOAD_DIR, OUTPUT_DIR are pathlib.Path instances."""
    from pdd_crawler.config import COOKIE_PATH, DOWNLOADS_DIR, OUTPUT_DIR

    # All should be Path instances
    assert isinstance(COOKIE_PATH, Path)
    assert isinstance(DOWNLOADS_DIR, Path)
    assert isinstance(OUTPUT_DIR, Path)

    # COOKIE_PATH should end with the expected filename
    assert COOKIE_PATH.name == "pdd_cookies.json"


def test_load_cookies_missing_file():
    """Test cookie_manager.load_cookies returns None for non-existent file."""
    from pdd_crawler.cookie_manager import load_cookies

    async def _async_test():
        async with async_playwright() as p:
            # Use a path that definitely doesn't exist
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

            # Create test data matching expected structure
            test_data = {
                "scraped_at": "2025-03-09T10:30:00",
                "url": "https://mms.pinduoduo.com/home/",
                "page_title": "Test Page",
                "data": {
                    "item_0": "Test Item 1",
                    "item_1": "Test Item 2",
                },
            }

            # Save the data
            result_path = await save_home_data(test_data, output_dir)

            # Verify file was created
            assert result_path.exists()
            assert result_path.suffix == ".json"
            assert "home_data_" in result_path.name

            # Verify file content
            with open(result_path, "r", encoding="utf-8") as f:
                saved_data = json.load(f)

            assert saved_data["scraped_at"] == test_data["scraped_at"]
            assert saved_data["url"] == test_data["url"]
            assert saved_data["page_title"] == test_data["page_title"]
            assert saved_data["data"]["item_0"] == "Test Item 1"
            assert saved_data["data"]["item_1"] == "Test Item 2"

    asyncio.run(_async_test())


def test_cli_help():
    """Use subprocess.run to verify `python -m pdd_crawler --help` returns 0 and shows all 4 options."""
    result = subprocess.run(
        ["python", "-m", "pdd_crawler", "--help"],
        capture_output=True,
        text=True,
    )

    # Should exit with code 0
    assert result.returncode == 0

    # Check help output contains all 4 CLI options
    help_text = result.stdout
    assert "--login" in help_text
    assert "--scrape-home" in help_text
    assert "--export-bills" in help_text
    assert "--all" in help_text

    # Verify it's the expected help format
    assert "PDD Crawler" in help_text or "pdd_crawler" in help_text.lower()
