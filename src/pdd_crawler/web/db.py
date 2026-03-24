"""PostgreSQL connection pool and schema management.

Configuration via environment variables:
    PG_DSN      Full DSN string, e.g.:
                postgresql://user:pass@localhost:5432/pdd_crawler
    PG_HOST     (default: localhost)
    PG_PORT     (default: 5432)
    PG_USER     (default: postgres)
    PG_PASSWORD (default: "")
    PG_DATABASE (default: pdd_crawler)

PG_DSN takes priority over individual vars.
"""

from __future__ import annotations

import os
from typing import Generator

import psycopg2
from psycopg2 import pool as pg_pool
from psycopg2.extras import RealDictCursor


def _build_dsn() -> str:
    dsn = os.environ.get("PG_DSN")
    if dsn:
        return dsn
    host = os.environ.get("PG_HOST", "localhost")
    port = os.environ.get("PG_PORT", "5432")
    user = os.environ.get("PG_USER", "postgres")
    password = os.environ.get("PG_PASSWORD", "")
    database = os.environ.get("PG_DATABASE", "pdd_crawler")
    return f"postgresql://{user}:{password}@{host}:{port}/{database}"


_pool: pg_pool.ThreadedConnectionPool | None = None


def get_pool() -> pg_pool.ThreadedConnectionPool:
    global _pool
    if _pool is None:
        raise RuntimeError("Database pool not initialised. Call init_db() first.")
    return _pool


def get_conn():
    """Context manager: borrow a connection from the pool."""
    import contextlib

    @contextlib.contextmanager
    def _cm():
        conn = get_pool().getconn()
        try:
            yield conn
        except Exception:
            conn.rollback()
            raise
        else:
            conn.commit()
        finally:
            get_pool().putconn(conn)

    return _cm()


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
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_shop_date
    ON shop_daily_reports (shop_name, data_date);
"""


def init_db() -> None:
    """Initialise connection pool and ensure schema exists."""
    global _pool
    dsn = _build_dsn()
    # On Windows, psycopg2 reads pgpass.conf which may be GBK-encoded,
    # causing UnicodeDecodeError. Always redirect to NUL (Windows /dev/null)
    # since the DSN already contains credentials.
    if os.name == "nt":
        os.environ["PGPASSFILE"] = "NUL"
    _pool = pg_pool.ThreadedConnectionPool(minconn=1, maxconn=10, dsn=dsn)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(_DDL)
    print(f"[DB] Connected to PostgreSQL — pool ready (dsn={dsn.split('@')[-1]})")


def close_db() -> None:
    global _pool
    if _pool:
        _pool.closeall()
        _pool = None
        print("[DB] Connection pool closed")
