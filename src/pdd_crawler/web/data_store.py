"""PostgreSQL-backed data store for shop daily reports.

Drop-in replacement for the previous JSON-file store.
All public interfaces (DataStore methods + module-level helpers) are unchanged.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from pdd_crawler.web import db


_FIELD_MAP = {
    "成交金额": "payment_amount",
    "全站推广": "promotion_cost",
    "评价有礼+跨店满返（营销账户导出）": "marketing_cost",
    "技术服务费（支出+返还净额）": "tech_service_fee",
    "平台返还（维权）": "platform_refund",
    "售后费用（扣款中售后+其他中售后）": "after_sale_cost",
    "其他费用（排除技术服务费和售后后的剩余）": "other_cost",
}

_WEEKDAYS = ["一", "二", "三", "四", "五", "六", "日"]

_NUMERIC_FIELDS = [
    "payment_amount",
    "promotion_cost",
    "marketing_cost",
    "after_sale_cost",
    "tech_service_fee",
    "other_cost",
    "platform_refund",
]


def _weekday(data_date: str) -> str:
    try:
        d = date.fromisoformat(data_date)
        return "周" + _WEEKDAYS[d.weekday()]
    except Exception:
        return ""


def _row_to_dict(rec: dict) -> dict:
    """Convert a DB record (RealDictRow) to a plain dict with serialisable types."""
    row: dict[str, Any] = dict(rec)
    # psycopg2 returns DATE as datetime.date — serialise to ISO string
    if isinstance(row.get("data_date"), date):
        row["data_date"] = row["data_date"].isoformat()
    # NUMERIC → float
    for f in _NUMERIC_FIELDS:
        if f in row:
            row[f] = float(row[f])
    # Drop internal timestamp
    row.pop("created_at", None)
    return row


class DataStore:
    """PostgreSQL-backed store — same public API as the old JSON-file store."""

    # ── Meta ─────────────────────────────────────────────

    def get_shops(self) -> list[str]:
        sql = """
            SELECT DISTINCT shop_name
            FROM shop_daily_reports
            ORDER BY shop_name
        """
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                return [r[0] for r in cur.fetchall()]

    def get_months(self) -> list[str]:
        sql = """
            SELECT DISTINCT to_char(data_date, 'YYYY-MM') AS month
            FROM shop_daily_reports
            ORDER BY month DESC
        """
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                return [r[0] for r in cur.fetchall()]

    # ── Query ─────────────────────────────────────────────

    def query(self, shops: list[str] | None, month: str | None) -> list[dict]:
        from psycopg2.extras import RealDictCursor

        conditions: list[str] = []
        params: list[Any] = []

        if shops:
            conditions.append("shop_name = ANY(%s)")
            params.append(shops)
        if month:
            conditions.append("to_char(data_date, 'YYYY-MM') = %s")
            params.append(month)

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        sql = f"""
            SELECT id, shop_name, data_date, weekday,
                   payment_amount, promotion_cost, marketing_cost,
                   after_sale_cost, tech_service_fee, other_cost, platform_refund
            FROM shop_daily_reports
            {where}
            ORDER BY shop_name, data_date
        """
        with db.get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql, params or None)
                return [_row_to_dict(r) for r in cur.fetchall()]

    # ── CRUD ──────────────────────────────────────────────

    def add_row(self, data: dict) -> dict:
        from psycopg2.extras import RealDictCursor

        row_id = str(uuid.uuid4())
        shop_name = str(data.get("shop_name", ""))
        data_date = str(data.get("data_date", ""))
        weekday = _weekday(data_date)

        fields = {f: float(data.get(f, 0) or 0) for f in _NUMERIC_FIELDS}

        sql = """
            INSERT INTO shop_daily_reports
                (id, shop_name, data_date, weekday,
                 payment_amount, promotion_cost, marketing_cost,
                 after_sale_cost, tech_service_fee, other_cost, platform_refund)
            VALUES
                (%(id)s, %(shop_name)s, %(data_date)s, %(weekday)s,
                 %(payment_amount)s, %(promotion_cost)s, %(marketing_cost)s,
                 %(after_sale_cost)s, %(tech_service_fee)s, %(other_cost)s,
                 %(platform_refund)s)
            RETURNING id, shop_name, data_date, weekday,
                      payment_amount, promotion_cost, marketing_cost,
                      after_sale_cost, tech_service_fee, other_cost, platform_refund
        """
        params = {
            "id": row_id,
            "shop_name": shop_name,
            "data_date": data_date,
            "weekday": weekday,
            **fields,
        }

        with db.get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql, params)
                return _row_to_dict(cur.fetchone())

    def update_row(self, row_id: str, updates: dict) -> dict | None:
        from psycopg2.extras import RealDictCursor

        allowed = {f for f in _NUMERIC_FIELDS if f in updates}
        if not allowed:
            # Nothing to update — just return the existing row
            return self._get_row(row_id)

        set_clause = ", ".join(f"{f} = %({f})s" for f in allowed)
        sql = f"""
            UPDATE shop_daily_reports
            SET {set_clause}
            WHERE id = %(id)s
            RETURNING id, shop_name, data_date, weekday,
                      payment_amount, promotion_cost, marketing_cost,
                      after_sale_cost, tech_service_fee, other_cost, platform_refund
        """
        params: dict[str, Any] = dict(id=row_id)
        params.update({f: float(updates[f] or 0) for f in allowed})

        with db.get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql, params)
                rec = cur.fetchone()
                return _row_to_dict(rec) if rec else None

    def _get_row(self, row_id: str) -> dict | None:
        from psycopg2.extras import RealDictCursor

        sql = """
            SELECT id, shop_name, data_date, weekday,
                   payment_amount, promotion_cost, marketing_cost,
                   after_sale_cost, tech_service_fee, other_cost, platform_refund
            FROM shop_daily_reports WHERE id = %s
        """
        with db.get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql, (row_id,))
                rec = cur.fetchone()
                return _row_to_dict(rec) if rec else None

    def delete_row(self, row_id: str) -> bool:
        sql = "DELETE FROM shop_daily_reports WHERE id = %s"
        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (row_id,))
                return cur.rowcount > 0

    # ── Import helpers ────────────────────────────────────

    def import_json_data(self, report: dict) -> dict:
        """Upsert a single cleaned report dict (Chinese or English keys)."""
        from psycopg2.extras import RealDictCursor

        shop_name = str(report.get("店铺名称", "") or report.get("shop_name", ""))
        data_date = str(report.get("数据日期", "") or report.get("data_date", ""))
        if not shop_name or not data_date:
            return {}

        row_data: dict[str, Any] = {"shop_name": shop_name, "data_date": data_date}
        for cn_key, en_key in _FIELD_MAP.items():
            if cn_key in report:
                row_data[en_key] = float(report[cn_key] or 0)
            elif en_key in report:
                row_data[en_key] = float(report[en_key] or 0)

        weekday = _weekday(data_date)
        fields = {f: row_data.get(f, 0.0) for f in _NUMERIC_FIELDS}

        sql = """
            INSERT INTO shop_daily_reports
                (id, shop_name, data_date, weekday,
                 payment_amount, promotion_cost, marketing_cost,
                 after_sale_cost, tech_service_fee, other_cost, platform_refund)
            VALUES
                (%(id)s, %(shop_name)s, %(data_date)s, %(weekday)s,
                 %(payment_amount)s, %(promotion_cost)s, %(marketing_cost)s,
                 %(after_sale_cost)s, %(tech_service_fee)s, %(other_cost)s,
                 %(platform_refund)s)
            ON CONFLICT (shop_name, data_date) DO UPDATE SET
                weekday          = EXCLUDED.weekday,
                payment_amount   = EXCLUDED.payment_amount,
                promotion_cost   = EXCLUDED.promotion_cost,
                marketing_cost   = EXCLUDED.marketing_cost,
                after_sale_cost  = EXCLUDED.after_sale_cost,
                tech_service_fee = EXCLUDED.tech_service_fee,
                other_cost       = EXCLUDED.other_cost,
                platform_refund  = EXCLUDED.platform_refund
            RETURNING id, shop_name, data_date, weekday,
                      payment_amount, promotion_cost, marketing_cost,
                      after_sale_cost, tech_service_fee, other_cost, platform_refund
        """
        params = {
            "id": str(uuid.uuid4()),
            "shop_name": shop_name,
            "data_date": data_date,
            "weekday": weekday,
            **fields,
        }

        with db.get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql, params)
                return _row_to_dict(cur.fetchone())

    def import_from_json_file(self, content: str) -> int:
        import json

        try:
            data = json.loads(content)
        except Exception:
            return 0
        if isinstance(data, dict):
            data = [data]
        if not isinstance(data, list):
            return 0
        count = 0
        for item in data:
            if isinstance(item, dict):
                if self.import_json_data(item):
                    count += 1
        return count


# Global singleton
store = DataStore()


# Module-level helper (used by clean_api.py)
def import_json_data(report: dict) -> dict:
    return store.import_json_data(report)
