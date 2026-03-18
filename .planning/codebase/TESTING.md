# TESTING — Test Structure & Practices

## Framework

- **Test Runner**: pytest >= 7.0
- **No async test support**: Uses `asyncio.run()` wrapper

## Test Location

```
tests/
├── __init__.py
├── test_smoke.py           # Main test suite (170 lines)
└── test_cookie_manager.py  # Cookie manager tests
```

## Test Patterns

### Import Tests
```python
def test_all_imports():
    """Test that all modules can be imported without error."""
    from pdd_crawler import config
    from pdd_crawler import cookie_manager
    ...
    assert config is not None
```

### Configuration Tests
```python
def test_browser_config():
    """Test that get_browser_config() returns a BrowserConfig with stealth enabled."""
    from pdd_crawler.cookie_manager import get_browser_config
    cfg = get_browser_config()
    assert isinstance(cfg, BrowserConfig)
    assert cfg.enable_stealth is True

def test_config_urls():
    """Assert all URL constants contain correct domains."""
    from pdd_crawler.config import PDD_HOME_URL, ...
    assert "mms.pinduoduo.com" in PDD_HOME_URL
```

### Function Existence
```python
def test_scrape_home_function_exists():
    import inspect
    from pdd_crawler.home_scraper import scrape_home
    assert callable(scrape_home)
    assert inspect.iscoroutinefunction(scrape_home)
```

### Async Tests
```python
def test_load_cookies_missing_file():
    """Test validate_cookies returns False for non-existent cookie file."""
    async def _async_test():
        missing_path = Path("/tmp/nonexistent_path_xyz/cookies.json")
        result = await validate_cookies(missing_path)
        assert result is False
    asyncio.run(_async_test())
```

### CLI Tests
```python
def test_cli_help():
    """Verify `python -m pdd_crawler --help` returns 0."""
    result = subprocess.run(
        ["python", "-m", "pdd_crawler", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "--host" in result.stdout
```

## Running Tests

```bash
# Run all tests
pytest

# Run specific file
pytest tests/test_smoke.py

# Run with verbose output
pytest -v
```

## Test Coverage

- **Import verification**: All modules importable
- **Config validation**: URL constants, browser config
- **Function signatures**: Callable check, coroutine check
- **CLI**: Help command works
- **No unit tests**: No mocking of crawl4ai/Playwright

## Gaps

- No mocking of browser/crawler (integration tests only)
- No API endpoint tests (would require test client)
- No data cleaning tests
- No session isolation tests
