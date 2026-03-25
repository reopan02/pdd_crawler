"""JST (聚水潭) sales data import API endpoints.

Provides upload → preview → commit workflow for Excel imports.
"""

from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from typing import Optional

from pdd_crawler.web import jst_import

router = APIRouter(prefix="/data/jst", tags=["jst-import"])


# ── Upload ────────────────────────────────────────────────


@router.post("/upload")
async def upload_xlsx(file: UploadFile = File(...)):
    """Upload a JST Excel file and parse it.

    Returns upload_token and basic parse stats.
    """
    if not file.filename or not file.filename.endswith(".xlsx"):
        raise HTTPException(status_code=422, detail="仅支持 .xlsx 文件")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=422, detail="文件为空")

    try:
        parsed = jst_import.parse_xlsx(content, file.filename)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    upload_token = str(uuid.uuid4())
    await jst_import.register_upload(upload_token, file.filename, parsed)

    return {
        "upload_token": upload_token,
        "filename": file.filename,
        "total_rows": parsed["total_rows"],
        "parsed_rows": len(parsed["rows"]),
        "parse_errors": parsed["errors"][:10],
    }


# ── Preview ───────────────────────────────────────────────


@router.post("/preview")
async def preview_import(
    upload_token: str = Form(...),
    biz_date: Optional[str] = Form(None),
):
    """Preview matching results for a previously uploaded file.

    Uses upload_token from the upload step.
    biz_date defaults to today if not provided.
    """
    cached = jst_import.get_uploaded_payload(upload_token)
    if not cached:
        raise HTTPException(status_code=404, detail="上传数据已过期，请重新上传")

    parsed = cached["parsed"]
    filename = cached["filename"]

    # Parse biz_date
    if biz_date:
        try:
            bd = date.fromisoformat(biz_date)
        except ValueError:
            raise HTTPException(status_code=422, detail="日期格式错误，应为 YYYY-MM-DD")
    else:
        bd = date.today()

    try:
        result = await jst_import.build_preview(
            upload_token=upload_token,
            parsed=parsed,
            filename=filename,
            biz_date=bd,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"预览失败: {e}")

    return result


# ── Commit ────────────────────────────────────────────────


@router.post("/commit")
async def commit_import(
    upload_token: str = Form(...),
    preview_id: str = Form(...),
):
    """Commit previewed data to the database.

    Idempotent: same upload_token won't insert twice.
    """
    try:
        result = await jst_import.commit_import(upload_token, preview_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"写入失败: {e}")

    return result


# ── Import log ────────────────────────────────────────────


@router.get("/import-log/{log_id}")
async def get_import_log(log_id: str):
    """Query import log details."""
    log = await jst_import.get_import_log(log_id)
    if not log:
        raise HTTPException(status_code=404, detail="导入日志不存在")
    return log


@router.get("/import-log")
async def get_import_log_by_token(upload_token: str):
    log = await jst_import.get_import_log_by_token(upload_token)
    if not log:
        raise HTTPException(status_code=404, detail="导入日志不存在")
    return log
