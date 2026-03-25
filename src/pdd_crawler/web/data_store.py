"""PostgreSQL-backed data store for shop daily reports (asyncpg).

Drop-in replacement for the previous JSON-file store.
All public interfaces are async.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
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
    "sales_amount",
    "refund_amount",
    "sales_cost",
    "refund_cost",
    "sales_order_count",
    "freight_expense",
]


def _weekday(data_date: str) -> str:
    try:
        d = date.fromisoformat(data_date)
        return "周" + _WEEKDAYS[d.weekday()]
    except Exception:
        return ""


def _rec_to_dict(rec) -> dict:
    """Convert an asyncpg Record to a plain serialisable dict."""
    row: dict[str, Any] = dict(rec)
    if isinstance(row.get("data_date"), date):
        row["data_date"] = row["data_date"].isoformat()
    for f in _NUMERIC_FIELDS:
        if f in row and isinstance(row[f], Decimal):
            row[f] = float(row[f])
    row.pop("created_at", None)
    return row


class DataStore:
    """asyncpg-backed store — same public API as the old JSON-file store."""

    # ── Meta ─────────────────────────────────────────────

    async def get_shops(self) -> list[str]:
        async with db.get_conn() as conn:
            rows = await conn.fetch(
                "SELECT DISTINCT shop_name FROM shop_daily_reports ORDER BY shop_name"
            )
            return [r["shop_name"] for r in rows]

    async def get_months(self) -> list[str]:
        async with db.get_conn() as conn:
            rows = await conn.fetch(
                "SELECT DISTINCT to_char(data_date, 'YYYY-MM') AS month "
                "FROM shop_daily_reports ORDER BY month DESC"
            )
            return [r["month"] for r in rows]

    # ── Query ─────────────────────────────────────────────

    async def query(self, shops: list[str] | None, month: str | None) -> list[dict]:
        conditions: list[str] = []
        params: list[Any] = []
        idx = 1

        if shops:
            conditions.append(f"shop_name = ANY(${idx})")
            params.append(shops)
            idx += 1
        if month:
            conditions.append(f"to_char(data_date, 'YYYY-MM') = ${idx}")
            params.append(month)
            idx += 1

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        sql = f"""
            SELECT id, shop_name, data_date, weekday,
                   payment_amount, promotion_cost, marketing_cost,
                   after_sale_cost, tech_service_fee, other_cost, platform_refund,
                   sales_amount, refund_amount, sales_cost, refund_cost,
                   sales_order_count, freight_expense
            FROM shop_daily_reports
            {where}
            ORDER BY shop_name, data_date
        """
        async with db.get_conn() as conn:
            rows = await conn.fetch(sql, *params)
            return [_rec_to_dict(r) for r in rows]

    # ── CRUD ──────────────────────────────────────────────

    async def add_row(self, data: dict) -> dict:
        row_id = str(uuid.uuid4())
        shop_name = str(data.get("shop_name", ""))
        data_date = str(data.get("data_date", ""))
        weekday = _weekday(data_date)
        fields = {f: float(data.get(f, 0) or 0) for f in _NUMERIC_FIELDS}

        sql = """
            INSERT INTO shop_daily_reports
                (id, shop_name, data_date, weekday,
                 payment_amount, promotion_cost, marketing_cost,
                 after_sale_cost, tech_service_fee, other_cost, platform_refund,
                 sales_amount, refund_amount, sales_cost, refund_cost,
                 sales_order_count, freight_expense)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17)
            ON CONFLICT (shop_name, data_date) DO UPDATE SET
                weekday          = EXCLUDED.weekday,
                payment_amount   = EXCLUDED.payment_amount,
                promotion_cost   = EXCLUDED.promotion_cost,
                marketing_cost   = EXCLUDED.marketing_cost,
                after_sale_cost  = EXCLUDED.after_sale_cost,
                tech_service_fee = EXCLUDED.tech_service_fee,
                other_cost       = EXCLUDED.other_cost,
                platform_refund  = EXCLUDED.platform_refund,
                sales_amount     = EXCLUDED.sales_amount,
                refund_amount    = EXCLUDED.refund_amount,
                sales_cost       = EXCLUDED.sales_cost,
                refund_cost      = EXCLUDED.refund_cost,
                sales_order_count = EXCLUDED.sales_order_count,
                freight_expense  = EXCLUDED.freight_expense
            RETURNING id, shop_name, data_date, weekday,
                      payment_amount, promotion_cost, marketing_cost,
                      after_sale_cost, tech_service_fee, other_cost, platform_refund,
                      sales_amount, refund_amount, sales_cost, refund_cost,
                      sales_order_count, freight_expense
        """
        async with db.get_conn() as conn:
            rec = await conn.fetchrow(
                sql,
                row_id,
                shop_name,
                date.fromisoformat(data_date),
                weekday,
                fields["payment_amount"],
                fields["promotion_cost"],
                fields["marketing_cost"],
                fields["after_sale_cost"],
                fields["tech_service_fee"],
                fields["other_cost"],
                fields["platform_refund"],
                fields["sales_amount"],
                fields["refund_amount"],
                fields["sales_cost"],
                fields["refund_cost"],
                int(fields.get("sales_order_count", 0)),
                fields["freight_expense"],
            )
            return _rec_to_dict(rec)

    async def update_row(self, row_id: str, updates: dict) -> dict | None:
        allowed = [f for f in _NUMERIC_FIELDS if f in updates]
        if not allowed:
            return await self._get_row(row_id)

        set_clause = ", ".join(f"{f} = ${i + 2}" for i, f in enumerate(allowed))
        sql = f"""
            UPDATE shop_daily_reports
            SET {set_clause}
            WHERE id = $1
            RETURNING id, shop_name, data_date, weekday,
                      payment_amount, promotion_cost, marketing_cost,
                      after_sale_cost, tech_service_fee, other_cost, platform_refund,
                      sales_amount, refund_amount, sales_cost, refund_cost,
                      sales_order_count, freight_expense
        """
        values = [float(updates[f] or 0) for f in allowed]
        async with db.get_conn() as conn:
            rec = await conn.fetchrow(sql, row_id, *values)
            return _rec_to_dict(rec) if rec else None

    async def _get_row(self, row_id: str) -> dict | None:
        sql = """
            SELECT id, shop_name, data_date, weekday,
                   payment_amount, promotion_cost, marketing_cost,
                   after_sale_cost, tech_service_fee, other_cost, platform_refund,
                   sales_amount, refund_amount, sales_cost, refund_cost,
                   sales_order_count, freight_expense
            FROM shop_daily_reports WHERE id = $1
        """
        async with db.get_conn() as conn:
            rec = await conn.fetchrow(sql, row_id)
            return _rec_to_dict(rec) if rec else None

    async def delete_row(self, row_id: str) -> bool:
        async with db.get_conn() as conn:
            result = await conn.execute(
                "DELETE FROM shop_daily_reports WHERE id = $1", row_id
            )
            return result == "DELETE 1"

    # ── Import helpers ────────────────────────────────────

    async def import_json_data(self, report: dict) -> dict:
        """Upsert a single cleaned report dict (Chinese or English keys)."""
        shop_name = str(report.get("店铺名称", "") or report.get("shop_name", ""))
        data_date = str(report.get("数据日期", "") or report.get("data_date", ""))
        if not shop_name or not data_date:
            return {}

        row_data: dict[str, Any] = {}
        for cn_key, en_key in _FIELD_MAP.items():
            if cn_key in report:
                row_data[en_key] = float(report[cn_key] or 0)
            elif en_key in report:
                row_data[en_key] = float(report[en_key] or 0)

        weekday = _weekday(data_date)
        fields = {f: row_data.get(f, 0.0) for f in _NUMERIC_FIELDS}
        row_id = str(uuid.uuid4())

        sql = """
            INSERT INTO shop_daily_reports
                (id, shop_name, data_date, weekday,
                 payment_amount, promotion_cost, marketing_cost,
                 after_sale_cost, tech_service_fee, other_cost, platform_refund,
                 sales_amount, refund_amount, sales_cost, refund_cost,
                 sales_order_count, freight_expense)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17)
            ON CONFLICT (shop_name, data_date) DO UPDATE SET
                weekday          = EXCLUDED.weekday,
                payment_amount   = EXCLUDED.payment_amount,
                promotion_cost   = EXCLUDED.promotion_cost,
                marketing_cost   = EXCLUDED.marketing_cost,
                after_sale_cost  = EXCLUDED.after_sale_cost,
                tech_service_fee = EXCLUDED.tech_service_fee,
                other_cost       = EXCLUDED.other_cost,
                platform_refund  = EXCLUDED.platform_refund,
                sales_amount     = EXCLUDED.sales_amount,
                refund_amount    = EXCLUDED.refund_amount,
                sales_cost       = EXCLUDED.sales_cost,
                refund_cost      = EXCLUDED.refund_cost,
                sales_order_count = EXCLUDED.sales_order_count,
                freight_expense  = EXCLUDED.freight_expense
            RETURNING id, shop_name, data_date, weekday,
                      payment_amount, promotion_cost, marketing_cost,
                      after_sale_cost, tech_service_fee, other_cost, platform_refund,
                      sales_amount, refund_amount, sales_cost, refund_cost,
                      sales_order_count, freight_expense
        """
        async with db.get_conn() as conn:
            rec = await conn.fetchrow(
                sql,
                row_id,
                shop_name,
                date.fromisoformat(data_date),
                weekday,
                fields["payment_amount"],
                fields["promotion_cost"],
                fields["marketing_cost"],
                fields["after_sale_cost"],
                fields["tech_service_fee"],
                fields["other_cost"],
                fields["platform_refund"],
                fields["sales_amount"],
                fields["refund_amount"],
                fields["sales_cost"],
                fields["refund_cost"],
                int(fields.get("sales_order_count", 0)),
                fields["freight_expense"],
            )
            return _rec_to_dict(rec) if rec else {}

    async def import_from_json_file(self, content: str) -> int:
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
                if await self.import_json_data(item):
                    count += 1
        return count


# Global singleton
store = DataStore()


# Module-level helper (used by clean_api.py)
async def import_json_data(report: dict) -> dict:
    return await store.import_json_data(report)
