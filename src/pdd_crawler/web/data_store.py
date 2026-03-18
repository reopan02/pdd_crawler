"""Persistent data store backed by SQLite.

Stores cleaned daily reports in a local SQLite database so data survives
server restarts.  The schema mirrors the export project's daily_data table.

The DB file lives at ``<project_root>/data/data.db``.
"""

from __future__ import annotations

import sqlite3
import threading
from calendar import monthrange
from datetime import datetime
from pathlib import Path
from typing import Any

from pdd_crawler import config

DB_DIR = config.PROJECT_ROOT / "data"
DB_PATH = DB_DIR / "data.db"

# Chinese field name → DB column mapping (same as export project)
FIELD_MAP: dict[str, str] = {
    "店铺名称": "shop_name",
    "数据日期": "data_date",
    "采集日期": "collect_date",
    "成交金额": "payment_amount",
    "全站推广": "promotion_cost",
    "评价有礼+跨店满返（营销账户导出）": "marketing_cost",
    "技术服务费（支出+返还净额）": "tech_service_fee",
    "平台返还（维权）": "platform_refund",
    "售后费用（扣款中售后+其他中售后）": "after_sale_cost",
    "其他费用（排除技术服务费和售后后的剩余）": "other_cost",
}

_WEEKDAYS = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]

_lock = threading.Lock()
_conn: sqlite3.Connection | None = None


# ── DB accessor ──────────────────────────────────────────


def _db() -> sqlite3.Connection:
    if _conn is None:
        init_db()
    assert _conn is not None
    return _conn


# ── Shop persistence (must be defined before init_db) ────


def _load_shops_into_config() -> None:
    """Load shops from DB and merge into config.CHROME_ENDPOINTS.

    DB shops take precedence over hardcoded defaults (by shop_id).
    """
    assert _conn is not None
    rows = _conn.execute("SELECT * FROM shops ORDER BY created_at").fetchall()
    existing_ids = {ep.shop_id for ep in config.CHROME_ENDPOINTS}

    for row in rows:
        ep = config.ChromeEndpoint(
            shop_id=row["shop_id"],
            shop_name=row["shop_name"],
            cdp_url=row["cdp_url"],
            vnc_url=row["vnc_url"],
        )
        if row["shop_id"] in existing_ids:
            # DB version overrides hardcoded
            config.remove_endpoint(row["shop_id"])
        config.CHROME_ENDPOINTS.append(ep)

    if rows:
        print(f"[DataStore] 从数据库加载了 {len(rows)} 个店铺配置")


# ── Lifecycle ────────────────────────────────────────────


def init_db() -> None:
    """Create the database and tables if they don't exist."""
    global _conn
    DB_DIR.mkdir(parents=True, exist_ok=True)
    _conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    _conn.row_factory = sqlite3.Row
    _conn.execute("PRAGMA journal_mode=WAL")
    _conn.execute("""
        CREATE TABLE IF NOT EXISTS daily_data (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            shop_name   TEXT NOT NULL,
            data_date   TEXT NOT NULL,
            collect_date TEXT NOT NULL DEFAULT '',
            payment_amount  REAL DEFAULT 0,
            promotion_cost  REAL DEFAULT 0,
            marketing_cost  REAL DEFAULT 0,
            tech_service_fee REAL DEFAULT 0,
            platform_refund  REAL DEFAULT 0,
            after_sale_cost  REAL DEFAULT 0,
            other_cost       REAL DEFAULT 0,
            created_at  TEXT DEFAULT (datetime('now', 'localtime')),
            updated_at  TEXT DEFAULT (datetime('now', 'localtime')),
            UNIQUE(shop_name, data_date)
        )
    """)
    _conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_daily_shop_date ON daily_data(shop_name, data_date)"
    )
    _conn.execute("CREATE INDEX IF NOT EXISTS idx_daily_date ON daily_data(data_date)")

    # ── Shops table (dynamic shop management) ──
    _conn.execute("""
        CREATE TABLE IF NOT EXISTS shops (
            shop_id   TEXT PRIMARY KEY,
            shop_name TEXT NOT NULL,
            cdp_url   TEXT NOT NULL,
            vnc_url   TEXT NOT NULL DEFAULT '',
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        )
    """)

    _conn.commit()

    # Load persisted shops into config.CHROME_ENDPOINTS
    _load_shops_into_config()

    print(f"[DataStore] SQLite 数据库已初始化: {DB_PATH}")


# ── Import ───────────────────────────────────────────────


def import_json_data(
    json_array: list[dict[str, Any]] | dict[str, Any],
) -> list[dict[str, str]]:
    """Parse cleaned report dicts and upsert into DB.

    Accepts either a single dict or a list of dicts.  Keys can be Chinese
    field names (from clean_api output) or English column names.
    """
    items = json_array if isinstance(json_array, list) else [json_array]
    results: list[dict[str, str]] = []
    conn = _db()

    with _lock:
        for item in items:
            row: dict[str, Any] = {}
            for cn_key, db_col in FIELD_MAP.items():
                if cn_key in item:
                    row[db_col] = item[cn_key]
                elif db_col in item:
                    row[db_col] = item[db_col]
                else:
                    row[db_col] = (
                        ""
                        if db_col in ("shop_name", "data_date", "collect_date")
                        else 0
                    )

            if not row.get("shop_name") or not row.get("data_date"):
                continue

            conn.execute(
                """
                INSERT INTO daily_data
                    (shop_name, data_date, collect_date,
                     payment_amount, promotion_cost, marketing_cost,
                     tech_service_fee, platform_refund, after_sale_cost, other_cost,
                     updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now','localtime'))
                ON CONFLICT(shop_name, data_date) DO UPDATE SET
                    collect_date     = excluded.collect_date,
                    payment_amount   = excluded.payment_amount,
                    promotion_cost   = excluded.promotion_cost,
                    marketing_cost   = excluded.marketing_cost,
                    tech_service_fee = excluded.tech_service_fee,
                    platform_refund  = excluded.platform_refund,
                    after_sale_cost  = excluded.after_sale_cost,
                    other_cost       = excluded.other_cost,
                    updated_at       = datetime('now','localtime')
                """,
                (
                    row["shop_name"],
                    row["data_date"],
                    row.get("collect_date", ""),
                    float(row.get("payment_amount", 0) or 0),
                    float(row.get("promotion_cost", 0) or 0),
                    float(row.get("marketing_cost", 0) or 0),
                    float(row.get("tech_service_fee", 0) or 0),
                    float(row.get("platform_refund", 0) or 0),
                    float(row.get("after_sale_cost", 0) or 0),
                    float(row.get("other_cost", 0) or 0),
                ),
            )
            results.append(
                {"shop": row["shop_name"], "date": row["data_date"], "status": "ok"}
            )

        conn.commit()
    return results


# ── Query helpers ────────────────────────────────────────


def _rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(r) for r in rows]


def get_shops() -> list[str]:
    """Return all distinct shop names, sorted."""
    rows = (
        _db()
        .execute("SELECT DISTINCT shop_name FROM daily_data ORDER BY shop_name")
        .fetchall()
    )
    return [r["shop_name"] for r in rows]


def get_available_months() -> list[str]:
    """Return all distinct YYYY-MM months, newest first."""
    rows = (
        _db()
        .execute(
            "SELECT DISTINCT substr(data_date, 1, 7) AS month FROM daily_data ORDER BY month DESC"
        )
        .fetchall()
    )
    return [r["month"] for r in rows]


def query_data(
    shops: list[str] | None = None,
    month: str | None = None,
) -> list[dict[str, Any]]:
    """Query data rows with optional shop/month filters."""
    sql = "SELECT * FROM daily_data WHERE 1=1"
    params: list[Any] = []

    if shops:
        placeholders = ",".join("?" for _ in shops)
        sql += f" AND shop_name IN ({placeholders})"
        params.extend(shops)

    if month:
        sql += " AND data_date LIKE ?"
        params.append(f"{month}%")

    sql += " ORDER BY shop_name, data_date ASC"
    rows = _db().execute(sql, params).fetchall()
    return _rows_to_dicts(rows)


# ── Single-row CRUD ──────────────────────────────────────


def add_row(data: dict[str, Any]) -> dict[str, Any]:
    """Insert or upsert a single row. Returns the saved row."""
    conn = _db()
    with _lock:
        conn.execute(
            """
            INSERT INTO daily_data
                (shop_name, data_date, collect_date,
                 payment_amount, promotion_cost, marketing_cost,
                 tech_service_fee, platform_refund, after_sale_cost, other_cost,
                 updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now','localtime'))
            ON CONFLICT(shop_name, data_date) DO UPDATE SET
                collect_date     = excluded.collect_date,
                payment_amount   = excluded.payment_amount,
                promotion_cost   = excluded.promotion_cost,
                marketing_cost   = excluded.marketing_cost,
                tech_service_fee = excluded.tech_service_fee,
                platform_refund  = excluded.platform_refund,
                after_sale_cost  = excluded.after_sale_cost,
                other_cost       = excluded.other_cost,
                updated_at       = datetime('now','localtime')
            """,
            (
                data["shop_name"],
                data["data_date"],
                data.get("collect_date", data.get("data_date", "")),
                float(data.get("payment_amount", 0) or 0),
                float(data.get("promotion_cost", 0) or 0),
                float(data.get("marketing_cost", 0) or 0),
                float(data.get("tech_service_fee", 0) or 0),
                float(data.get("platform_refund", 0) or 0),
                float(data.get("after_sale_cost", 0) or 0),
                float(data.get("other_cost", 0) or 0),
            ),
        )
        conn.commit()

    # Return the row (may have been inserted or updated)
    row = conn.execute(
        "SELECT * FROM daily_data WHERE shop_name = ? AND data_date = ?",
        (data["shop_name"], data["data_date"]),
    ).fetchone()
    return dict(row) if row else {}


def update_row(row_id: int, data: dict[str, Any]) -> dict[str, Any] | None:
    """Update fields of an existing row by id."""
    conn = _db()
    updatable = [
        "shop_name",
        "data_date",
        "collect_date",
        "payment_amount",
        "promotion_cost",
        "marketing_cost",
        "tech_service_fee",
        "platform_refund",
        "after_sale_cost",
        "other_cost",
    ]
    set_clauses: list[str] = []
    params: list[Any] = []

    for field in updatable:
        if field in data:
            set_clauses.append(f"{field} = ?")
            params.append(
                float(data[field])
                if field not in ("shop_name", "data_date", "collect_date")
                else data[field]
            )

    if not set_clauses:
        return None

    set_clauses.append("updated_at = datetime('now','localtime')")
    params.append(row_id)

    with _lock:
        conn.execute(
            f"UPDATE daily_data SET {', '.join(set_clauses)} WHERE id = ?",
            params,
        )
        conn.commit()

    row = conn.execute("SELECT * FROM daily_data WHERE id = ?", (row_id,)).fetchone()
    return dict(row) if row else None


def delete_row(row_id: int) -> dict[str, Any] | None:
    """Delete a row by id. Returns the deleted row or None."""
    conn = _db()
    row = conn.execute("SELECT * FROM daily_data WHERE id = ?", (row_id,)).fetchone()
    if row is None:
        return None
    with _lock:
        conn.execute("DELETE FROM daily_data WHERE id = ?", (row_id,))
        conn.commit()
    return dict(row)


# ── Template data for Excel export ───────────────────────


def _get_weekday_cn(date_str: str) -> str:
    """Return Chinese weekday name for a YYYY-MM-DD string."""
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d")
        return _WEEKDAYS[d.weekday()]
    except (ValueError, IndexError):
        return ""


def _get_month_dates(month: str) -> list[str]:
    """Return all YYYY-MM-DD dates in a given YYYY-MM month."""
    try:
        year, mon = int(month[:4]), int(month[5:7])
    except (ValueError, IndexError):
        return []
    days = monthrange(year, mon)[1]
    return [f"{year}-{mon:02d}-{d:02d}" for d in range(1, days + 1)]


def build_template_data(shop_name: str, month: str) -> dict[str, Any]:
    """Build a full-month template for one shop, filling missing dates with zeros.

    Returns the same structure as the export project's buildTemplateData().
    """
    rows = query_data(shops=[shop_name], month=month)
    data_map = {r["data_date"]: r for r in rows}
    all_dates = _get_month_dates(month)

    numeric_fields = [
        "payment_amount",
        "promotion_cost",
        "marketing_cost",
        "tech_service_fee",
        "platform_refund",
        "after_sale_cost",
        "other_cost",
    ]

    totals = {f: 0.0 for f in numeric_fields}
    template_rows: list[dict[str, Any]] = []

    for date_str in all_dates:
        r = data_map.get(date_str)
        weekday = _get_weekday_cn(date_str)
        display_date = date_str.replace("-", "/")

        if r:
            row_data: dict[str, Any] = {
                "date": display_date,
                "weekday": weekday,
                "has_data": True,
            }
            for f in numeric_fields:
                val = float(r.get(f, 0) or 0)
                row_data[f] = val
                totals[f] += val
        else:
            row_data = {
                "date": display_date,
                "weekday": weekday,
                "has_data": False,
                **{f: 0 for f in numeric_fields},
            }

        template_rows.append(row_data)

    try:
        mon_num = int(month[5:7])
        year = int(month[:4])
    except (ValueError, IndexError):
        mon_num = 0
        year = 0

    return {
        "shopName": shop_name,
        "month": f"{mon_num}月份",
        "year": year,
        "rows": template_rows,
        "totals": totals,
    }


# ── Shop persistence (CRUD — load is defined above init_db) ──


def save_shop(shop_id: str, shop_name: str, cdp_url: str, vnc_url: str) -> None:
    """Persist a shop to SQLite and register in config."""
    conn = _db()
    with _lock:
        conn.execute(
            """
            INSERT INTO shops (shop_id, shop_name, cdp_url, vnc_url)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(shop_id) DO UPDATE SET
                shop_name = excluded.shop_name,
                cdp_url   = excluded.cdp_url,
                vnc_url   = excluded.vnc_url
            """,
            (shop_id, shop_name, cdp_url, vnc_url),
        )
        conn.commit()

    config.add_endpoint(
        config.ChromeEndpoint(
            shop_id=shop_id,
            shop_name=shop_name,
            cdp_url=cdp_url,
            vnc_url=vnc_url,
        )
    )


def delete_shop(shop_id: str) -> bool:
    """Remove a shop from SQLite and config. Returns True if found."""
    conn = _db()
    with _lock:
        cursor = conn.execute("DELETE FROM shops WHERE shop_id = ?", (shop_id,))
        conn.commit()

    config.remove_endpoint(shop_id)
    return cursor.rowcount > 0


def list_persisted_shops() -> list[dict[str, str]]:
    """Return all shops from the DB."""
    conn = _db()
    rows = conn.execute("SELECT * FROM shops ORDER BY created_at").fetchall()
    return [dict(r) for r in rows]
