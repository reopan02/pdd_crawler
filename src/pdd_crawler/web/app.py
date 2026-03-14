"""FastAPI application — PDD Crawler Web Interface.

Serves the React SPA and provides REST + SSE APIs for cookie management,
crawl task orchestration, and data cleaning.

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
    print("[Web] PDD Crawler Web 启动")
    yield
    print("[Web] PDD Crawler Web 关闭")


app = FastAPI(
    title="PDD Crawler",
    description="拼多多商家后台数据采集工具 — Web 界面",
    version="0.2.0",
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
    return {"status": "ok"}


# ── Import and register API routers ──────────────────────
from pdd_crawler.web.cookie_api import router as cookie_router  # noqa: E402
from pdd_crawler.web.task_api import router as task_router  # noqa: E402
from pdd_crawler.web.clean_api import router as clean_router  # noqa: E402

app.include_router(cookie_router, prefix="/api")
app.include_router(task_router, prefix="/api")
app.include_router(clean_router, prefix="/api")


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
