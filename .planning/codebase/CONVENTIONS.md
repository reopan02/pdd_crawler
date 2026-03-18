# CONVENTIONS — Code Style & Patterns

## Style

- **Formatter**: Black (line length: 88)
- **Linter**: flake8
- **Type Checker**: mypy with per-file disables

## Type Annotations

```python
# Required for function signatures
from __future__ import annotations

def func(param: str) -> dict[str, object]:
    ...
```

## Dataclasses

Use `@dataclass` for simple data containers:

```python
from dataclasses import dataclass, field
from typing import Any

@dataclass
class TaskResult:
    task_id: str
    task_type: str
    status: str = "pending"
    data: dict[str, Any] = field(default_factory=dict)
```

## Async Patterns

```python
# Use asyncio.run() for sync entry points
async def main():
    ...

if __name__ == "__main__":
    asyncio.run(main())

# Use typing.Coroutine for async function annotations
from typing import Coroutine

def foo() -> Coroutine[Any, Any, str]:
    ...
```

## Error Handling

- **Raised Exceptions**: Use `RuntimeError`, `TimeoutError`, `AttributeError`
- **Print for Logging**: `print(f"[Module] Message: {detail}")`
- **No Structured Logging**: Print-based for simplicity

## Browser/Crawler Access Pattern

The code uses internal crawl4ai APIs with type ignores:

```python
# pyright-disable at file level for crawl4ai internals
# pyright: reportMissingImports=false
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig

# Access internal browser manager (requires runtime inspection)
page, _ctx = await crawler.crawler_strategy.browser_manager.get_page(
    crawlerRunConfig=CrawlerRunConfig(session_id=session_id)
)
```

## Import Organization

```python
# 1. Standard library
from __future__ import annotations
import asyncio
from pathlib import Path

# 2. Third-party
from fastapi import FastAPI
from crawl4ai import AsyncWebCrawler

# 3. Local
from pdd_crawler import config
from pdd_crawler.home_scraper import scrape_home
```

## Naming

| Type | Convention | Example |
|------|------------|---------|
| Modules | snake_case | `cookie_manager.py` |
| Classes | PascalCase | `SessionStore`, `TaskResult` |
| Functions | snake_case | `validate_cookies()`, `scrape_home()` |
| Constants | UPPER_SNAKE_CASE | `PDD_HOME_URL`, `BROWSER_CONFIG` |
| Private | leading_underscore | `_get_current_url()` |

## File Headers

```python
"""Module name — brief description."""

from __future__ import annotations
# pyright: reportMissingImports=false, ...
```

## Type Ignore Pattern

Use per-line type ignores for known crawl4ai/Playwright issues:

```python
result = await func()  # type: ignore[attr-defined]
```

## Docstrings

Google-style for public APIs:

```python
def scrape_home(crawler: AsyncWebCrawler, session_id: str) -> dict[str, object]:
    """Navigate to PDD home and extract all visible dashboard metrics.

    Args:
        crawler: An active crawl4ai crawler instance.
        session_id: Session identifier for the crawler.

    Returns:
        A dict containing scraped_at, url, page_title, shop_name, and data.

    Raises:
        RuntimeError: If the page redirects to the login URL.
    """
```
