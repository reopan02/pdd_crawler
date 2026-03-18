# ARCHITECTURE — System Design

## Pattern: Layered REST API with Async Crawling

```
┌─────────────────────────────────────────────────────────┐
│                    FastAPI App                          │
│         (CORS, Router Mounting, Static Files)          │
└───────────────────────┬─────────────────────────────────┘
                        │
        ┌───────────────┼───────────────┐
        │               │               │
        ▼               ▼               ▼
   ┌─────────┐    ┌──────────┐    ┌─────────┐
   │ Cookie  │    │  Task    │    │  Clean  │
   │  API    │    │   API    │    │   API   │
   └────┬────┘    └────┬─────┘    └────┬────┘
        │              │               │
        └──────────────┼───────────────┘
                       ▼
              ┌────────────────┐
              │  SessionStore  │ (In-Memory)
              │  - Cookies     │
              │  - Tasks       │
              │  - Results     │
              └────────────────┘
                       │
        ┌──────────────┴──────────────┐
        ▼                              ▼
   ┌──────────────────┐    ┌────────────────────┐
   │ cookie_manager   │    │ crawl4ai_bill_     │
   │ (Browser/Cookie) │    │ exporter           │
   └────────┬─────────┘    └──────────┬─────────┘
            │                          │
            └──────────┬───────────────┘
                       ▼
              ┌────────────────┐
              │ crawl4ai +     │
              │ Playwright     │
              │ (Chromium)     │
              └────────────────┘
```

## Key Components

### Web Layer (`src/pdd_crawler/web/`)
| File | Responsibility |
|------|----------------|
| `app.py` | FastAPI app, CORS, router mounting |
| `deps.py` | Shared dependencies (session ID, browser semaphore) |
| `session_store.py` | In-memory multi-user session storage |
| `cookie_api.py` | Cookie upload, validate, QR login |
| `task_api.py` | Crawl task management, SSE progress |
| `clean_api.py` | Data cleaning, report generation |

### Core Layer (`src/pdd_crawler/`)
| File | Responsibility |
|------|----------------|
| `config.py` | URLs, timeouts, browser config, constants |
| `cookie_manager.py` | Browser creation, cookie validation, QR login |
| `home_scraper.py` | Homepage data extraction via JS injection |
| `crawl4ai_bill_exporter.py` | Bill export with SSO flow |

## Data Flow

1. **Upload Cookie** → Stored in `SessionStore` (memory)
2. **Start Task** → Create `TaskResult`, return `task_id`
3. **SSE Progress** → Real-time updates via `/tasks/{id}/progress`
4. **Execute Crawl**:
   - Create crawl4ai crawler with cookie
   - Navigate to PDD pages
   - Extract data via JS evaluation
5. **Store Results** → In `TaskResult.data`
6. **Download** → Stream directly to browser (no disk write)

## Multi-User Isolation

- **Session ID**: Via `X-Session-ID` header (or query param)
- **Default**: `default` session if not specified
- **Isolation**: Each session has separate cookies, tasks, results
- **Concurrency**: `asyncio.Semaphore(2)` limits simultaneous browsers

## Entry Points

```bash
# CLI (starts web server)
python -m pdd_crawler --host 0.0.0.0 --port 8089

# Direct uvicorn
uvicorn pdd_crawler.web.app:app --host 0.0.0.0 --port 8000
```
