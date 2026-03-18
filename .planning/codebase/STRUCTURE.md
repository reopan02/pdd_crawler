# STRUCTURE — Directory Layout

```
pdd_crawler/
├── src/pdd_crawler/
│   ├── __main__.py              # CLI entry (python -m pdd_crawler)
│   ├── config.py                # All configuration constants
│   ├── cookie_manager.py        # Browser/auth management
│   ├── home_scraper.py          # Homepage scraping
│   ├── crawl4ai_bill_exporter.py # Bill export logic
│   ├── __init__.py
│   └── web/
│       ├── app.py               # FastAPI application
│       ├── deps.py              # Shared dependencies
│       ├── session_store.py     # In-memory session storage
│       ├── cookie_api.py        # Cookie endpoints
│       ├── task_api.py          # Task endpoints + SSE
│       ├── clean_api.py         # Data cleaning endpoints
│       ├── run.py               # Alternative web entry
│       └── static/
│           └── index.html       # React SPA frontend
├── tests/
│   ├── __init__.py
│   ├── test_smoke.py            # Main test suite
│   └── test_cookie_manager.py   # Cookie manager tests
├── pyproject.toml               # Project config
├── README.md                    # Documentation
└── start.sh                     # Linux/WSL daemon script
```

## Key File Locations

| Component | File |
|-----------|------|
| Main entry | `src/pdd_crawler/__main__.py` |
| FastAPI app | `src/pdd_crawler/web/app.py` |
| Config | `src/pdd_crawler/config.py` |
| Session store | `src/pdd_crawler/web/session_store.py` |
| Tests | `tests/test_smoke.py` |

## Naming Conventions

- **Modules**: `snake_case.py`
- **Classes**: `PascalCase`
- **Functions**: `snake_case()`
- **Constants**: `UPPER_SNAKE_CASE`
- **Dataclasses**: `PascalCase` with `Entry`, `Result`, `Session` suffixes

## API Routes

| Prefix | File | Routes |
|--------|------|--------|
| `/api` | `cookie_api.py` | `/cookies/*`, `/qr-login/*` |
| `/api` | `task_api.py` | `/crawl/*`, `/tasks/*` |
| `/api` | `clean_api.py` | `/clean/*` |
| `/` | `app.py` | `/health`, static files |

## Data Structures

### SessionStore (`session_store.py`)
```python
@dataclass
class CookieEntry:
    cookie_id: str
    shop_name: str
    storage_state: dict
    status: str

@dataclass
class TaskResult:
    task_id: str
    task_type: str
    status: str
    progress: int
    message: str
    data: dict
    files: list
    error: str | None

@dataclass
class Session:
    session_id: str
    cookies: dict[str, CookieEntry]
    tasks: dict[str, TaskResult]
```
