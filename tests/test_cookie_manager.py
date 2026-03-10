"""Test cookie manager functionality, especially the save_storage_state function."""

from __future__ import annotations

import tempfile
from pathlib import Path
import pytest
import asyncio

from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig

from pdd_crawler import cookie_manager
from pdd_crawler import config


@pytest.mark.asyncio
async def test_save_storage_state_no_attribute_error():
    """Test that save_storage_state doesn't throw AttributeError due to missing default_context."""
    # Create a temporary cookie file
    with tempfile.NamedTemporaryFile(suffix="_cookies.json", delete=False) as f:
        temp_cookie_path = Path(f.name)
    
    try:
        # Create a crawler instance with headless mode
        crawler = await cookie_manager.create_crawler(
            headless=True,
            cookie_path=None
        )
        
        session_id = "test_session"
        
        # Perform a simple crawl to ensure browser and context are initialized
        await crawler.arun(
            url="https://example.com",
            config=CrawlerRunConfig(session_id=session_id)
        )
        
        # Now test save_storage_state - this should NOT throw AttributeError
        await cookie_manager.save_storage_state(
            crawler=crawler,
            session_id=session_id,
            cookie_path=temp_cookie_path
        )
        
        # Verify the cookie file was created
        assert temp_cookie_path.exists()
        assert temp_cookie_path.stat().st_size > 0
        
    finally:
        # Cleanup
        if 'crawler' in locals():
            await crawler.close()
        if temp_cookie_path.exists():
            try:
                temp_cookie_path.unlink()
            except OSError:
                pass


@pytest.mark.asyncio
async def test_save_storage_state_fallback_mechanism():
    """Test that save_storage_state can fallback to getting context from session."""
    with tempfile.NamedTemporaryFile(suffix="_cookies.json", delete=False) as f:
        temp_cookie_path = Path(f.name)
    
    try:
        crawler = await cookie_manager.create_crawler(
            headless=True,
            cookie_path=None
        )
        
        session_id = "test_fallback_session"
        
        # Initialize browser and session
        await crawler.arun(
            url="https://example.com",
            config=CrawlerRunConfig(session_id=session_id)
        )
        
        # Now call save_storage_state - it should work with either default_context or fallback
        await cookie_manager.save_storage_state(
            crawler=crawler,
            session_id=session_id,
            cookie_path=temp_cookie_path
        )
        
        assert temp_cookie_path.exists()
        
    finally:
        if 'crawler' in locals():
            await crawler.close()
        if temp_cookie_path.exists():
            try:
                temp_cookie_path.unlink()
            except OSError:
                pass


if __name__ == "__main__":
    # Run the test directly for quick verification
    asyncio.run(test_save_storage_state_no_attribute_error())
    print("✓ test_save_storage_state_no_attribute_error passed")
    
    asyncio.run(test_save_storage_state_fallback_mechanism())
    print("✓ test_save_storage_state_fallback_mechanism passed")
    
    print("\nAll tests passed!")
