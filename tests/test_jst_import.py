import asyncio
import json
import sys
from contextlib import asynccontextmanager
from datetime import date
from io import BytesIO
from pathlib import Path

from openpyxl import Workbook

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pdd_crawler.web import jst_import


def _build_workbook_bytes() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.append(["渠道", "销售金额", "退货金额", "销售成本", "退货成本", "销售单数", "运费支出"])
    ws.append(["Alpha Shop", 100, 5, 60, 2, 3, 8])
    ws.append(["#", 999, 0, 0, 0, 0, 0])
    ws.append(["Beta Shop", 88.5, 1.5, 40, 0, 2, 5])
    buffer = BytesIO()
    wb.save(buffer)
    wb.close()
    return buffer.getvalue()


class _FakeTransaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeConn:
    def __init__(self):
        self.logs_by_token: dict[str, dict] = {}
        self.unmatched_rows: list[dict] = []
        self.imported_keys: set[tuple[date, str, str]] = {
            (date(2026, 3, 20), "Beta Shop", "sales.xlsx"),
        }
        self.db_shops = ["Alpha Shop", "Beta Shop"]

    def transaction(self):
        return _FakeTransaction()

    async def fetch(self, query: str, *params):
        sql = " ".join(query.split())
        if "SELECT DISTINCT shop_name FROM shop_daily_reports" in sql:
            return [{"shop_name": name} for name in self.db_shops]
        if "SELECT biz_date, shop_name, source_file_name FROM jst_sales_imports" in sql:
            biz_date, filename = params
            return [
                {
                    "biz_date": row_biz_date,
                    "shop_name": shop_name,
                    "source_file_name": source_file_name,
                }
                for row_biz_date, shop_name, source_file_name in self.imported_keys
                if row_biz_date == biz_date and source_file_name == filename
            ]
        if "SELECT source_shop_name, reason, top_candidates FROM import_unmatched" in sql:
            import_log_id = params[0]
            return [
                row
                for row in self.unmatched_rows
                if row["import_log_id"] == import_log_id
            ]
        raise AssertionError(f"Unexpected fetch SQL: {sql}")

    async def fetchrow(self, query: str, *params):
        sql = " ".join(query.split())
        if "SELECT * FROM import_logs WHERE upload_token = $1" in sql:
            return self.logs_by_token.get(params[0])
        if "SELECT * FROM import_logs WHERE id = $1" in sql:
            for row in self.logs_by_token.values():
                if row["id"] == params[0]:
                    return row
            return None
        raise AssertionError(f"Unexpected fetchrow SQL: {sql}")

    async def execute(self, query: str, *params):
        sql = " ".join(query.split())
        if "INSERT INTO import_logs" in sql and len(params) == 6:
            log_id, filename, upload_token, total_rows, parse_error_count, error_details = params
            existing = self.logs_by_token.get(upload_token, {})
            self.logs_by_token[upload_token] = {
                "id": existing.get("id", log_id),
                "file_name": filename,
                "upload_token": upload_token,
                "upload_time": existing.get("upload_time", "2026-03-25T00:00:00+00:00"),
                "preview_time": None,
                "commit_time": None,
                "total_rows": total_rows,
                "matched_count": 0,
                "unmatched_count": 0,
                "ambiguous_count": 0,
                "to_insert_count": 0,
                "duplicate_count": 0,
                "parse_error_count": parse_error_count,
                "inserted_count": 0,
                "skipped_count": 0,
                "failed_count": 0,
                "status": "uploaded",
                "latest_preview_id": None,
                "committed_preview_id": None,
                "preview_biz_date": None,
                "error_details": error_details,
            }
            return "INSERT 0 1"
        if "INSERT INTO import_logs" in sql and len(params) == 13:
            (
                log_id,
                filename,
                upload_token,
                total_rows,
                matched_count,
                unmatched_count,
                ambiguous_count,
                to_insert_count,
                duplicate_count,
                parse_error_count,
                latest_preview_id,
                preview_biz_date,
                error_details,
            ) = params
            existing = self.logs_by_token.get(upload_token, {})
            self.logs_by_token[upload_token] = {
                **existing,
                "id": existing.get("id", log_id),
                "file_name": filename,
                "upload_token": upload_token,
                "preview_time": "2026-03-25T01:00:00+00:00",
                "commit_time": None,
                "total_rows": total_rows,
                "matched_count": matched_count,
                "unmatched_count": unmatched_count,
                "ambiguous_count": ambiguous_count,
                "to_insert_count": to_insert_count,
                "duplicate_count": duplicate_count,
                "parse_error_count": parse_error_count,
                "inserted_count": 0,
                "skipped_count": 0,
                "failed_count": 0,
                "status": "previewed",
                "latest_preview_id": latest_preview_id,
                "committed_preview_id": None,
                "preview_biz_date": preview_biz_date,
                "error_details": error_details,
            }
            return "INSERT 0 1"
        if "DELETE FROM import_unmatched WHERE import_log_id = $1" in sql:
            import_log_id = params[0]
            self.unmatched_rows = [
                row for row in self.unmatched_rows if row["import_log_id"] != import_log_id
            ]
            return "DELETE 1"
        if "INSERT INTO import_unmatched" in sql:
            row_id, import_log_id, source_shop_name, reason, top_candidates = params
            self.unmatched_rows.append(
                {
                    "id": row_id,
                    "import_log_id": import_log_id,
                    "source_shop_name": source_shop_name,
                    "reason": reason,
                    "top_candidates": top_candidates,
                }
            )
            return "INSERT 0 1"
        if "INSERT INTO jst_sales_imports" in sql:
            _, biz_date, shop_name, _, _, _, _, _, _, _, _, source_file_name = params
            key = (biz_date, shop_name, source_file_name)
            if key in self.imported_keys:
                return "INSERT 0 0"
            self.imported_keys.add(key)
            return "INSERT 0 1"
        if "UPDATE import_logs SET commit_time = now()" in sql:
            upload_token, inserted_count, skipped_count, failed_count, preview_id, error_details = params
            row = self.logs_by_token[upload_token]
            row.update(
                {
                    "commit_time": "2026-03-25T02:00:00+00:00",
                    "inserted_count": inserted_count,
                    "skipped_count": skipped_count,
                    "failed_count": failed_count,
                    "status": "committed",
                    "committed_preview_id": preview_id,
                    "error_details": error_details,
                }
            )
            return "UPDATE 1"
        raise AssertionError(f"Unexpected execute SQL: {sql}")


def _patch_fake_db(monkeypatch):
    fake_conn = _FakeConn()

    @asynccontextmanager
    async def _get_conn():
        yield fake_conn

    monkeypatch.setattr(jst_import.db, "get_conn", _get_conn)
    return fake_conn


def test_parse_xlsx_keeps_only_required_fields():
    parsed = jst_import.parse_xlsx(_build_workbook_bytes(), "sales.xlsx")

    assert parsed["total_rows"] == 2
    assert len(parsed["rows"]) == 2
    assert parsed["rows"][0] == {
        "source_shop_name": "Alpha Shop",
        "sales_amount": 100,
        "refund_amount": 5,
        "sales_cost": 60,
        "refund_cost": 2,
        "sales_order_count": 3,
        "freight_expense": 8,
    }


def test_preview_and_commit_enforce_latest_snapshot(monkeypatch):
    fake_conn = _patch_fake_db(monkeypatch)
    upload_cache_backup = dict(jst_import._upload_cache)
    preview_cache_backup = dict(jst_import._preview_cache)
    jst_import._upload_cache.clear()
    jst_import._preview_cache.clear()

    async def _run():
        parsed = {
            "rows": [
                {
                    "source_shop_name": "AlphaShop",
                    "sales_amount": 100,
                    "refund_amount": 1,
                    "sales_cost": 60,
                    "refund_cost": 0,
                    "sales_order_count": 2,
                    "freight_expense": 5,
                },
                {
                    "source_shop_name": "Beta Shop",
                    "sales_amount": 80,
                    "refund_amount": 0,
                    "sales_cost": 40,
                    "refund_cost": 0,
                    "sales_order_count": 1,
                    "freight_expense": 4,
                },
                {
                    "source_shop_name": "Gamma Store",
                    "sales_amount": 50,
                    "refund_amount": 0,
                    "sales_cost": 20,
                    "refund_cost": 0,
                    "sales_order_count": 1,
                    "freight_expense": 3,
                },
            ],
            "errors": [{"row": 9, "shop": "Broken", "error": "bad number"}],
            "total_rows": 3,
            "filename": "sales.xlsx",
        }
        await jst_import.register_upload("token-1", "sales.xlsx", parsed)

        preview1 = await jst_import.build_preview(
            upload_token="token-1",
            parsed=parsed,
            filename="sales.xlsx",
            biz_date=date(2026, 3, 20),
        )
        preview2 = await jst_import.build_preview(
            upload_token="token-1",
            parsed=parsed,
            filename="sales.xlsx",
            biz_date=date(2026, 3, 21),
        )

        assert preview1["stats"]["duplicate_count"] == 1
        assert preview2["stats"]["duplicate_count"] == 0
        assert preview2["stats"]["matched_count"] == 2
        assert preview2["stats"]["unmatched_count"] == 1
        assert preview2["stats"]["parse_error_count"] == 1
        assert preview2["unmatched_rows"][0]["source_shop_name"] == "Gamma Store"

        try:
            await jst_import.commit_import("token-1", preview1["preview_id"])
            raise AssertionError("old preview should not be committed")
        except ValueError as exc:
            assert "最近一次预览快照" in str(exc)

        committed = await jst_import.commit_import("token-1", preview2["preview_id"])
        assert committed["status"] == "committed"
        assert committed["inserted_count"] == 2
        assert committed["skipped_count"] == 0
        assert committed["failed_count"] == 0

        committed_again = await jst_import.commit_import("token-1", preview2["preview_id"])
        assert committed_again["status"] == "already_committed"
        assert committed_again["inserted_count"] == 2

        log = await jst_import.get_import_log_by_token("token-1")
        assert log is not None
        assert log["status"] == "committed"
        assert log["duplicate_count"] == 0
        assert log["unmatched_rows"][0]["reason"] in {"相似度不足", "歧义候选过近"}
        assert json.loads(fake_conn.unmatched_rows[0]["top_candidates"]) == log["unmatched_rows"][0]["top_candidates"]

    try:
        asyncio.run(_run())
    finally:
        jst_import._upload_cache.clear()
        jst_import._upload_cache.update(upload_cache_backup)
        jst_import._preview_cache.clear()
        jst_import._preview_cache.update(preview_cache_backup)
