# STACK — Technology Stack

## Languages & Runtime

| Category | Technology | Version/Notes |
|----------|------------|---------------|
| Language | Python | 3.8+ |
| Runtime | CPython | - |
| Type Checking | pyright | (per-file disables) |

## Frameworks & Libraries

### Web Framework
- **FastAPI** >= 0.110.0 — REST API framework
- **Uvicorn** >= 0.27.0 — ASGI server
- **SSE-Starlette** >= 1.6.0 — Server-Sent Events for progress updates

### Crawling & Browser
- **crawl4ai** >= 0.7.0 — AI-powered web crawler (wrapper around Playwright)
- **Playwright** >= 1.40 — Browser automation (Chromium only)

### Data & Utilities
- **python-multipart** >= 0.0.6 — Form data parsing
- **pytest** >= 7.0 — Test framework

### Dev Tools
- **black** — Code formatter
- **flake8** — Linter
- **mypy** — Type checker

## Configuration

### Project Metadata
- **Location**: `pyproject.toml`
- **Package Name**: `pdd_crawler`
- **Entry Points**:
  - `pdd_crawler` → `pdd_crawler.__main__:main` (CLI)
  - `pdd_web` → `pdd_crawler.web.run:main` (Web server)

### Package Structure
```toml
[tool.setuptools]
package-dir = {"" = "src"}

[tool.setuptools.packages.find]
where = ["src"]
```

### Browser Configuration (`src/pdd_crawler/config.py`)
```python
BROWSER_CONFIG = {
    "browser_type": "chromium",
    "headless": True,
    "enable_stealth": True,
    "viewport_width": 1920,
    "viewport_height": 1080,
    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36...",
    "extra_args": [
        "--disable-blink-features=AutomationControlled",
        "--no-sandbox",
        "--disable-infobars",
        "--disable-dev-shm-usage",
        "--lang=zh-CN",
        "--disable-features=IsolateOrigins,site-per-process",
    ],
}
```

## Environment

- **Python**: >= 3.8
- **Platform**: Cross-platform (Windows, Linux/WSL)
- **Browser**: Chromium (via Playwright)
