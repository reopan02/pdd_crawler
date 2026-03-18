"""Data management API endpoints.

Provides CRUD operations for daily shop data backed by SQLite, plus
JSON file upload and Excel export.  This is "步骤三 — 数据管理与导出".
"""

from __future__ import annotations

import json
from datetime import datetime
from io import BytesIO
from typing import Any

from fastapi import APIRouter, File, Request, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from pdd_crawler.web.deps import get_session_id
from pdd_crawler.web import data_store
from pdd_crawler.web.export_xlsx import generate_xlsx

router = APIRouter(tags=["data"])


# ── Shops / Months metadata ─────────────────────────────


@router.get("/data/shops")
async def get_shops(request: Request):
    """Get list of all shops with data."""
    return {"shops": data_store.get_shops()}


@router.get("/data/months")
async def get_months(request: Request):
    """Get list of all months with data."""
    return {"months": data_store.get_available_months()}


# ── Query ────────────────────────────────────────────────


@router.get("/data/query")
async def query_data(
    request: Request,
    shops: str | None = None,
    month: str | None = None,
):
    """Query data rows with filters."""
    shop_list = shops.split(",") if shops else None
    rows = data_store.query_data(shops=shop_list, month=month)
    return {"rows": rows}


# ── Upload JSON files ────────────────────────────────────


@router.post("/data/upload")
async def upload_data(request: Request, files: list[UploadFile] = File(...)):
    """Upload JSON files and import into the database.

    Each file should contain either a single dict or a list of dicts with
    Chinese field names (same format as clean_api output).
    """
    total = 0
    errors: list[str] = []

    for f in files:
        try:
            raw = await f.read()
            text = raw.decode("utf-8")
            content = json.loads(text)
            items = content if isinstance(content, list) else [content]
            results = data_store.import_json_data(items)
            total += len(results)
        except Exception as exc:
            errors.append(f"{f.filename}: {exc}")

    return {"success": True, "count": total, "errors": errors}


# ── Import cleaned reports (from step 2 clean) ──────────


@router.post("/data/import-reports")
async def import_reports(request: Request):
    """Import cleaned reports into the database (user-confirmed write).

    Body: {"reports": [{...}, ...]}
    Each report is a cleaned dict with Chinese keys.
    """
    body = await request.json()
    reports = body.get("reports", [])
    if not reports:
        raise HTTPException(status_code=422, detail="缺少 reports 数据")

    results = data_store.import_json_data(reports)
    return {"success": True, "imported": len(results)}


# ── Single-row CRUD ──────────────────────────────────────


@router.post("/data/rows")
async def add_row(request: Request):
    """Add a new data row."""
    body = await request.json()
    if not body.get("shop_name") or not body.get("data_date"):
        raise HTTPException(status_code=400, detail="店铺名称和数据日期为必填项")
    row = data_store.add_row(body)
    return {"success": True, "row": row}


@router.put("/data/rows/{row_id}")
async def update_row(request: Request, row_id: int):
    """Update an existing data row."""
    body = await request.json()
    row = data_store.update_row(row_id, body)
    if row is None:
        raise HTTPException(status_code=404, detail="Row not found")
    return {"success": True, "row": row}


@router.delete("/data/rows/{row_id}")
async def delete_row(request: Request, row_id: int):
    """Delete a data row."""
    deleted = data_store.delete_row(row_id)
    if deleted is None:
        raise HTTPException(status_code=404, detail="Row not found")
    return {"success": True}


# ── Export XLSX ──────────────────────────────────────────


@router.get("/data/export")
async def export_data(
    request: Request,
    shops: str | None = None,
    month: str | None = None,
):
    """Export data to a styled Excel workbook (one sheet per shop)."""
    if not month:
        raise HTTPException(status_code=400, detail="请指定月份")

    shop_list = shops.split(",") if shops else data_store.get_shops()
    if not shop_list:
        raise HTTPException(status_code=400, detail="没有可导出的数据")

    content = generate_xlsx(shop_list, month)

    filename = f"店铺数据_{month}.xlsx"
    return StreamingResponse(
        BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(content)),
        },
    )
