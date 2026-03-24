"""In-memory data store with JSON file persistence.

Stores shop daily report rows. Data is persisted to output/data_store.json.
"""

from __future__ import annotations

import json
import threading
import uuid
from datetime import date
from pathlib import Path
from typing import Any

_STORE_FILE = Path(__file__).parent.parent.parent.parent / "output" / "data_store.json"

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


def _weekday(data_date: str) -> str:
    try:
        d = date.fromisoformat(data_date)
        return "周" + _WEEKDAYS[d.weekday()]
    except Exception:
        return ""


class DataStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._rows: list[dict] = []
        self._load()

    def _load(self) -> None:
        try:
            if _STORE_FILE.exists():
                data = json.loads(_STORE_FILE.read_text(encoding="utf-8"))
                self._rows = data.get("rows", [])
        except Exception:
            self._rows = []

    def _save(self) -> None:
        try:
            _STORE_FILE.parent.mkdir(parents=True, exist_ok=True)
            _STORE_FILE.write_text(
                json.dumps({"rows": self._rows}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

    def get_shops(self) -> list[str]:
        with self._lock:
            seen: dict[str, None] = {}
            for r in self._rows:
                seen[r["shop_name"]] = None
            return list(seen.keys())

    def get_months(self) -> list[str]:
        with self._lock:
            months: set[str] = set()
            for r in self._rows:
                d = r.get("data_date", "")
                if len(d) >= 7:
                    months.add(d[:7])
            return sorted(months, reverse=True)

    def query(self, shops: list[str] | None, month: str | None) -> list[dict]:
        with self._lock:
            result = []
            for r in self._rows:
                if shops and r["shop_name"] not in shops:
                    continue
                if month and not r.get("data_date", "").startswith(month):
                    continue
                result.append(dict(r))
            result.sort(key=lambda x: (x["shop_name"], x["data_date"]))
            return result

    def add_row(self, data: dict) -> dict:
        row = {
            "id": str(uuid.uuid4()),
            "shop_name": str(data.get("shop_name", "")),
            "data_date": str(data.get("data_date", "")),
            "weekday": _weekday(str(data.get("data_date", ""))),
            "payment_amount": float(data.get("payment_amount", 0) or 0),
            "promotion_cost": float(data.get("promotion_cost", 0) or 0),
            "marketing_cost": float(data.get("marketing_cost", 0) or 0),
            "after_sale_cost": float(data.get("after_sale_cost", 0) or 0),
            "tech_service_fee": float(data.get("tech_service_fee", 0) or 0),
            "other_cost": float(data.get("other_cost", 0) or 0),
            "platform_refund": float(data.get("platform_refund", 0) or 0),
        }
        with self._lock:
            self._rows.append(row)
            self._save()
        return row

    def update_row(self, row_id: str, updates: dict) -> dict | None:
        numeric_fields = {
            "payment_amount", "promotion_cost", "marketing_cost",
            "after_sale_cost", "tech_service_fee", "other_cost", "platform_refund",
        }
        with self._lock:
            for r in self._rows:
                if r["id"] == row_id:
                    for k, v in updates.items():
                        if k in numeric_fields:
                            r[k] = float(v or 0)
                    self._save()
                    return dict(r)
        return None

    def delete_row(self, row_id: str) -> bool:
        with self._lock:
            before = len(self._rows)
            self._rows = [r for r in self._rows if r["id"] != row_id]
            if len(self._rows) < before:
                self._save()
                return True
        return False

    def import_json_data(self, report: dict) -> dict:
        shop_name = str(report.get("店铺名称", "") or report.get("shop_name", ""))
        data_date = str(report.get("数据日期", "") or report.get("data_date", ""))
        if not shop_name or not data_date:
            return {}
        row_data: dict[str, Any] = {"shop_name": shop_name, "data_date": data_date}
        for cn_key, en_key in _FIELD_MAP.items():
            if cn_key in report:
                row_data[en_key] = report[cn_key]
            elif en_key in report:
                row_data[en_key] = report[en_key]
        with self._lock:
            for r in self._rows:
                if r["shop_name"] == shop_name and r["data_date"] == data_date:
                    for k, v in row_data.items():
                        if k not in ("shop_name", "data_date"):
                            r[k] = float(v or 0)
                    r["weekday"] = _weekday(data_date)
                    self._save()
                    return dict(r)
        return self.add_row(row_data)

    def import_from_json_file(self, content: str) -> int:
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


store = DataStore()


def import_json_data(report: dict) -> dict:
    return store.import_json_data(report)
