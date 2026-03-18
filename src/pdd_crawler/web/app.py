"""FastAPI application — PDD Crawler Web Interface.

Architecture: Chrome containers (Docker) + CDP connections + FastAPI backend.
Each shop has a dedicated Chrome instance; operations use Playwright connect_over_cdp.

Run with: uvicorn pdd_crawler.web.app:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — startup/shutdown hooks."""
    from pdd_crawler.web.data_store import init_db
    from pdd_crawler.web.deps import chrome_pool

    init_db()
    await chrome_pool.startup()
    print("[Web] PDD Crawler Web 启动 (CDP 模式)")
    yield
    await chrome_pool.shutdown()
    print("[Web] PDD Crawler Web 关闭")


app = FastAPI(
    title="PDD Crawler",
    description="拼多多商家后台数据采集工具 — Web 界面 (CDP 模式)",
    version="0.3.0",
    lifespan=lifespan,
)

# CORS — allow all origins for LAN access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Health check ──────────────────────────────────────────
@app.get("/health")
async def health():
    from pdd_crawler.web.deps import chrome_pool

    shops = chrome_pool.list_shops()
    return {
        "status": "ok",
        "mode": "cdp",
        "shops": len(shops),
        "connected": sum(1 for s in shops if s["connected"]),
    }


# ── Import and register API routers ──────────────────────
from pdd_crawler.web.shop_api import router as shop_router  # noqa: E402
from pdd_crawler.web.task_api import router as task_router  # noqa: E402
from pdd_crawler.web.clean_api import router as clean_router  # noqa: E402
from pdd_crawler.web.data_api import router as data_router  # noqa: E402

app.include_router(shop_router, prefix="/api")
app.include_router(task_router, prefix="/api")
app.include_router(clean_router, prefix="/api")
app.include_router(data_router, prefix="/api")


# ── Static files (React SPA) — must be last ──────────────
if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
else:

    @app.get("/")
    async def root():
        return JSONResponse(
            {"message": "React frontend not built yet."},
            status_code=200,
        )
