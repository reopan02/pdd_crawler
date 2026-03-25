"""PostgreSQL connection pool and schema management (asyncpg).

Configuration via environment variables:
    PG_DSN      Full DSN string, e.g.:
                postgresql://user:pass@localhost:5432/pdd_crawler
    PG_HOST     (default: localhost)
    PG_PORT     (default: 5432)
    PG_USER     (default: postgres)
    PG_PASSWORD (default: "")
    PG_DATABASE (default: pdd_crawler)

PG_DSN takes priority over individual vars.

Uses asyncpg (pure-Python, no libpq) to avoid Windows GBK encoding issues.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any

import asyncpg


def _build_conn_kwargs() -> dict:
    dsn = os.environ.get("PG_DSN")
    if dsn:
        from urllib.parse import urlparse, unquote

        parsed = urlparse(dsn)
        return {
            "host": parsed.hostname or "localhost",
            "port": int(parsed.port or 5432),
            "user": unquote(parsed.username or "postgres"),
            "password": unquote(parsed.password or ""),
            "database": (parsed.path or "/pdd_crawler").lstrip("/"),
        }
    return {
        "host": os.environ.get("PG_HOST", "localhost"),
        "port": int(os.environ.get("PG_PORT", "5432")),
        "user": os.environ.get("PG_USER", "postgres"),
        "password": os.environ.get("PG_PASSWORD", ""),
        "database": os.environ.get("PG_DATABASE", "pdd_crawler"),
    }


_pool: asyncpg.Pool | None = None


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Database pool not initialised. Call init_db() first.")
    return _pool


@asynccontextmanager
async def get_conn():
    """Async context manager: acquire a connection from the pool."""
    async with get_pool().acquire() as conn:
        yield conn


_DDL = """
CREATE TABLE IF NOT EXISTS shop_daily_reports (
    id            TEXT PRIMARY KEY,
    shop_name     TEXT        NOT NULL,
    data_date     DATE        NOT NULL,
    weekday       TEXT        NOT NULL DEFAULT '',
    payment_amount   NUMERIC(14,2) NOT NULL DEFAULT 0,
    promotion_cost   NUMERIC(14,2) NOT NULL DEFAULT 0,
    marketing_cost   NUMERIC(14,2) NOT NULL DEFAULT 0,
    after_sale_cost  NUMERIC(14,2) NOT NULL DEFAULT 0,
    tech_service_fee NUMERIC(14,2) NOT NULL DEFAULT 0,
    other_cost       NUMERIC(14,2) NOT NULL DEFAULT 0,
    platform_refund  NUMERIC(14,2) NOT NULL DEFAULT 0,
    sales_amount     NUMERIC(14,2) NOT NULL DEFAULT 0,
    refund_amount    NUMERIC(14,2) NOT NULL DEFAULT 0,
    sales_cost       NUMERIC(14,2) NOT NULL DEFAULT 0,
    refund_cost      NUMERIC(14,2) NOT NULL DEFAULT 0,
    sales_order_count INTEGER      NOT NULL DEFAULT 0,
    freight_expense  NUMERIC(14,2) NOT NULL DEFAULT 0,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_shop_date
    ON shop_daily_reports (shop_name, data_date);

-- JST (聚水潭) sales import tables
CREATE TABLE IF NOT EXISTS jst_sales_imports (
    id                TEXT PRIMARY KEY,
    biz_date          DATE           NOT NULL,
    shop_name         TEXT           NOT NULL,
    shop_name_matched TEXT           NOT NULL,
    source_shop_name  TEXT           NOT NULL,
    sales_amount      NUMERIC(14,2) NOT NULL DEFAULT 0,
    refund_amount     NUMERIC(14,2) NOT NULL DEFAULT 0,
    sales_cost        NUMERIC(14,2) NOT NULL DEFAULT 0,
    refund_cost       NUMERIC(14,2) NOT NULL DEFAULT 0,
    sales_order_count INTEGER       NOT NULL DEFAULT 0,
    freight_expense   NUMERIC(14,2) NOT NULL DEFAULT 0,
    source_file_name  TEXT           NOT NULL DEFAULT '',
    created_at        TIMESTAMPTZ   NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_jst_biz_shop_file
    ON jst_sales_imports (biz_date, shop_name, source_file_name);

CREATE TABLE IF NOT EXISTS import_logs (
    id                  TEXT PRIMARY KEY,
    file_name           TEXT        NOT NULL,
    upload_token        TEXT        NOT NULL,
    upload_time         TIMESTAMPTZ NOT NULL DEFAULT now(),
    preview_time        TIMESTAMPTZ,
    commit_time         TIMESTAMPTZ,
    total_rows          INTEGER     NOT NULL DEFAULT 0,
    matched_count       INTEGER     NOT NULL DEFAULT 0,
    unmatched_count     INTEGER     NOT NULL DEFAULT 0,
    ambiguous_count     INTEGER     NOT NULL DEFAULT 0,
    to_insert_count     INTEGER     NOT NULL DEFAULT 0,
    duplicate_count     INTEGER     NOT NULL DEFAULT 0,
    inserted_count      INTEGER     NOT NULL DEFAULT 0,
    skipped_count       INTEGER     NOT NULL DEFAULT 0,
    failed_count        INTEGER     NOT NULL DEFAULT 0,
    parse_error_count   INTEGER     NOT NULL DEFAULT 0,
    status              TEXT        NOT NULL DEFAULT 'uploaded',
    latest_preview_id   TEXT,
    committed_preview_id TEXT,
    preview_biz_date    DATE,
    error_details       JSONB       NOT NULL DEFAULT '[]'::jsonb
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_import_upload_token
    ON import_logs (upload_token);

CREATE TABLE IF NOT EXISTS import_unmatched (
    id              TEXT PRIMARY KEY,
    import_log_id   TEXT        NOT NULL,
    source_shop_name TEXT       NOT NULL,
    reason          TEXT        NOT NULL DEFAULT '',
    top_candidates  JSONB       NOT NULL DEFAULT '[]'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_unmatched_log
    ON import_unmatched (import_log_id);
"""

_SHOP_REPORTS_MIGRATIONS = [
    ("sales_amount", "NUMERIC(14,2) NOT NULL DEFAULT 0"),
    ("refund_amount", "NUMERIC(14,2) NOT NULL DEFAULT 0"),
    ("sales_cost", "NUMERIC(14,2) NOT NULL DEFAULT 0"),
    ("refund_cost", "NUMERIC(14,2) NOT NULL DEFAULT 0"),
    ("sales_order_count", "INTEGER NOT NULL DEFAULT 0"),
    ("freight_expense", "NUMERIC(14,2) NOT NULL DEFAULT 0"),
]

_IMPORT_LOGS_MIGRATIONS = [
    ("parse_error_count", "INTEGER NOT NULL DEFAULT 0"),
    ("latest_preview_id", "TEXT"),
    ("committed_preview_id", "TEXT"),
    ("preview_biz_date", "DATE"),
    ("duplicate_count", "INTEGER NOT NULL DEFAULT 0"),
]


async def _migrate_shop_reports(conn) -> None:
    for col_name, col_def in _SHOP_REPORTS_MIGRATIONS:
        try:
            await conn.execute(
                f"ALTER TABLE shop_daily_reports ADD COLUMN IF NOT EXISTS {col_name} {col_def}"
            )
        except Exception:
            pass


async def _migrate_import_logs(conn) -> None:
    for col_name, col_def in _IMPORT_LOGS_MIGRATIONS:
        try:
            await conn.execute(
                f"ALTER TABLE import_logs ADD COLUMN IF NOT EXISTS {col_name} {col_def}"
            )
        except Exception:
            pass


async def init_db() -> None:
    """Initialise async connection pool and ensure schema exists."""
    global _pool
    kwargs = _build_conn_kwargs()
    try:
        _pool = await asyncpg.create_pool(
            min_size=1,
            max_size=10,
            timeout=10,
            command_timeout=30,
            ssl=False,
            **kwargs,
        )
        async with get_conn() as conn:
            await conn.execute(_DDL)
            await _migrate_shop_reports(conn)
            await _migrate_import_logs(conn)
        host = kwargs.get("host", "")
        database = kwargs.get("database", "")
        print(f"[DB] Connected to PostgreSQL — pool ready ({host}/{database})")
    except Exception as e:
        host = kwargs.get("host", "")
        port = kwargs.get("port", "")
        database = kwargs.get("database", "")
        user = kwargs.get("user", "")
        raise RuntimeError(
            "PostgreSQL 连接失败。"
            f" host={host} port={port} db={database} user={user}. "
            "请检查 PostgreSQL 是否启动、账号密码是否正确、以及 pg_hba.conf 是否允许本机连接。"
        ) from e


async def close_db() -> None:
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
        print("[DB] Connection pool closed")
