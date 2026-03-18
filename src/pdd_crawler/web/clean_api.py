"""Data cleaning API endpoints.

Refactored from clean_shop_data.py to work with in-memory data instead of files.
"""

from __future__ import annotations

import base64
import csv
import io
import json
import re
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse

from pdd_crawler.web.deps import get_session_id
from pdd_crawler.web.session_store import store
from pdd_crawler.web import data_store

router = APIRouter(tags=["clean"])

# ── Excluded descriptions (from clean_shop_data.py) ──────
EXCLUDED_DESCS = {
    "0010002|交易收入-订单收入",
    "0010005|交易收入-优惠券结算",
    "0020002|交易退款-订单退款",
    "0020005|交易退款-优惠券结算",
    "0070004|转账-广告账户",
    "0080001|提现-提现申请",
}


# ── Utility functions (from clean_shop_data.py) ──────────


def _parse_yesterday_value(text: str) -> float:
    m = re.search(r"昨日\s+([\d.]+)", text)
    return float(m.group(1)) if m else 0.0


def _parse_amount(val: str) -> float:
    try:
        return float(val) if val else 0.0
    except ValueError:
        return 0.0


def _read_csv_from_string(csv_text: str) -> tuple[list[str], list[list[str]]]:
    """Parse CSV from string content. Same logic as clean_shop_data.read_csv_rows."""
    reader = csv.reader(io.StringIO(csv_text))
    rows = list(reader)

    header_idx = None
    for i, row in enumerate(rows):
        if row and row[0] == "商户订单号":
            header_idx = i
            break
    if header_idx is None:
        return [], []

    header = rows[header_idx]
    data = [
        row
        for row in rows[header_idx + 1 :]
        if len(row) >= len(header)
        and not row[0].startswith("#")
        and any(cell.strip() for cell in row)
    ]
    return header, data


def _find_yesterday_value(items: dict, label: str) -> float:
    candidates = []
    for _, val in items.items():
        if not isinstance(val, str):
            continue
        if label in val and re.search(r"昨日\s+[\d.]+", val):
            candidates.append(val)
    if not candidates:
        return 0.0
    best = min(candidates, key=len)
    return _parse_yesterday_value(best)


# ── Core extraction functions (in-memory versions) ───────


def extract_home_data_from_dict(home_data: dict) -> dict:
    """Extract metrics from home_data dict (already in memory)."""
    items = home_data.get("data", {})
    return {
        "成交金额": _find_yesterday_value(items, "成交金额"),
        "全站推广": _find_yesterday_value(items, "推广花费"),
        "shop_name": home_data.get("shop_name", ""),
        "scraped_at": home_data.get("scraped_at", ""),
    }


def extract_marketing_from_csv(csv_text: str) -> dict:
    """Extract marketing data from CSV string content.

    The exported CSV already contains only yesterday's data (date selection
    happens at export time), so no date filtering is needed here.
    """
    if not csv_text:
        return {"评价有礼": 0.0, "跨店满返": 0.0}

    _, rows = _read_csv_from_string(csv_text)
    pingjia = 0.0
    kuadian = 0.0

    for row in rows:
        acct_type = row[2] if len(row) > 2 else ""
        expense = _parse_amount(row[4]) if len(row) > 4 else 0.0
        if acct_type == "评价有礼":
            pingjia += abs(expense)
        elif acct_type == "跨店日常满返":
            kuadian += abs(expense)

    return {"评价有礼": pingjia, "跨店满返": kuadian}


def _extract_date_from_bill_csv(csv_text: str) -> str:
    """Extract the data date (YYYY-MM-DD) from the bill CSV's entry time column.

    The bill CSV is already filtered to a single day at export time, so the
    date from any row's "入账时间" column represents the data date.  This
    avoids relying on the local system clock or scraped_at timestamps.

    Returns '' if no valid date can be extracted.
    """
    if not csv_text:
        return ""
    _, rows = _read_csv_from_string(csv_text)
    for row in rows:
        entry_time = row[1] if len(row) > 1 else ""
        m = re.search(r"(\d{4}-\d{2}-\d{2})", entry_time)
        if m:
            return m.group(1)
    return ""


def extract_bill_from_csv(csv_text: str) -> dict:
    """Extract bill data from CSV string content."""
    if not csv_text:
        return {"技术服务费": 0.0, "售后费用": 0.0, "其他费用": 0.0, "平台返还": 0.0}

    _, rows = _read_csv_from_string(csv_text)

    service_fee = 0.0
    after_sales = 0.0
    other_expense = 0.0
    return_fee = 0.0

    for row in rows:
        if len(row) < 7:
            continue
        income = _parse_amount(row[2])
        expense = _parse_amount(row[3])
        acct_type = row[4]
        desc = row[6]

        if desc in EXCLUDED_DESCS:
            continue

        if acct_type == "技术服务费" and desc == "0030002|技术服务费-基础技术服务费":
            service_fee += income + expense
            continue

        if acct_type == "其他" and desc == "0030001|技术服务费-技术服务费":
            service_fee += income + expense
            continue

        if desc.startswith("0040"):
            after_sales += abs(expense)
            continue

        if acct_type == "其他" and "售后" in desc and expense < 0:
            after_sales += abs(expense)
            continue

        if acct_type == "其他" and income > 0:
            return_fee += income
            continue

        if acct_type == "其他" and expense < 0:
            other_expense += abs(expense)
            continue

    return {
        "技术服务费": round(service_fee, 2),
        "售后费用": round(after_sales, 2),
        "其他费用": round(other_expense, 2),
        "平台返还": round(return_fee, 2),
    }


def process_shop_data(
    home_data: dict,
    bill_csv: str | None = None,
    marketing_csv: str | None = None,
) -> dict:
    """Process a single shop's data and return cleaned report."""
    home = extract_home_data_from_dict(home_data)

    # Derive data_date from the bill CSV's entry time column (PDD server time).
    # This avoids any dependency on the local system clock / timezone.
    data_date = _extract_date_from_bill_csv(bill_csv or "")

    scraped_at = home.get("scraped_at", "")
    if scraped_at:
        collect_date = scraped_at[:10]  # 'YYYY-MM-DD' prefix of ISO timestamp
    else:
        collect_date = ""

    marketing = extract_marketing_from_csv(marketing_csv or "")
    bill = extract_bill_from_csv(bill_csv or "")

    return {
        "店铺名称": home.get("shop_name") or "未知店铺",
        "数据日期": data_date,
        "采集日期": collect_date,
        "成交金额": home["成交金额"],
        "全站推广": home["全站推广"],
        "评价有礼+跨店满返（营销账户导出）": round(
            marketing["评价有礼"] + marketing["跨店满返"], 2
        ),
        "技术服务费（支出+返还净额）": bill["技术服务费"],
        "平台返还（维权）": bill["平台返还"],
        "售后费用（扣款中售后+其他中售后）": bill["售后费用"],
        "其他费用（排除技术服务费和售后后的剩余）": bill["其他费用"],
    }


def _decode_text(content: Any) -> str | None:
    if isinstance(content, bytes):
        for encoding in ("gb18030", "utf-8"):
            try:
                return content.decode(encoding)
            except Exception:
                continue
        return None
    if isinstance(content, str):
        return content
    return None


def _normalize_home_data(home_data: Any) -> list[dict]:
    if isinstance(home_data, dict):
        if any(key in home_data for key in ("scraped_at", "url", "page_title")):
            return [home_data]
        nested = home_data.get("data")
        if isinstance(nested, dict):
            return [nested]
        return []
    if isinstance(home_data, list):
        normalized = []
        for item in home_data:
            if isinstance(item, dict) and isinstance(item.get("data"), dict):
                normalized.append(item["data"])
            elif isinstance(item, dict):
                normalized.append(item)
        return normalized
    return []


def _match_task_csv_files(
    task_files: list[dict], shop_name: str, single_shop: bool
) -> tuple[str | None, str | None]:
    bill_csv = None
    marketing_csv = None
    shop_prefix = f"{shop_name.lower()}_" if shop_name else ""

    for f in task_files:
        filename = str(f.get("filename", "")).lower()
        if not filename:
            continue
        if not single_shop and shop_prefix and not filename.startswith(shop_prefix):
            continue
        text = _decode_text(f.get("content"))
        if text is None:
            continue
        if "bill-detail" in filename and "marketing" not in filename:
            bill_csv = text
        elif "marketing" in filename:
            marketing_csv = text
    return bill_csv, marketing_csv


# ── API Endpoints ────────────────────────────────────────


@router.post("/clean")
async def clean_data(request: Request):
    """Clean shop data from direct input.

    Body: {
        "home_data": {...},                    # Required: home scrape result
        "bill_csv_base64": "...",              # Optional: GB18030 CSV as base64
        "marketing_csv_base64": "..."          # Optional: GB18030 CSV as base64
    }
    """
    body = await request.json()

    home_data = body.get("home_data")
    if not home_data:
        raise HTTPException(status_code=422, detail="缺少 home_data")

    bill_csv = None
    if body.get("bill_csv_base64"):
        try:
            raw = base64.b64decode(body["bill_csv_base64"])
            bill_csv = raw.decode("gb18030")
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"bill_csv 解码失败: {e}")

    marketing_csv = None
    if body.get("marketing_csv_base64"):
        try:
            raw = base64.b64decode(body["marketing_csv_base64"])
            marketing_csv = raw.decode("gb18030")
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"marketing_csv 解码失败: {e}")

    report = process_shop_data(home_data, bill_csv, marketing_csv)
    return {"report": report}


@router.post("/clean/from-task/{task_id}")
async def clean_from_task(request: Request, task_id: str):
    """Clean data from a completed crawl task's results."""
    session_id = get_session_id(request)
    task = store.get_task(session_id, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task.status != "completed":
        raise HTTPException(status_code=400, detail="任务未完成")

    raw_home_data = task.data.get("home_data")
    if not raw_home_data:
        raise HTTPException(status_code=400, detail="任务中没有首页数据")
    home_data_list = _normalize_home_data(raw_home_data)
    if not home_data_list:
        raise HTTPException(status_code=400, detail="任务首页数据格式不正确")

    reports = []
    single_shop = len(home_data_list) == 1
    for home_data in home_data_list:
        shop_name = str(home_data.get("shop_name", ""))
        bill_csv, marketing_csv = _match_task_csv_files(
            task.files, shop_name, single_shop
        )
        reports.append(process_shop_data(home_data, bill_csv, marketing_csv))

    # Auto-import cleaned data into persistent store
    _auto_import_reports(reports)

    return {"report": reports, "reports": reports, "count": len(reports)}


def _auto_import_reports(reports: list[dict]) -> int:
    """Auto-import cleaned reports into the persistent data store."""
    count = 0
    for report in reports:
        if report.get("数据日期") and report.get("店铺名称"):
            data_store.import_json_data(report)
            count += 1
    return count


@router.post("/clean/download")
async def download_clean_report(request: Request):
    """Generate and download a cleaned report as JSON file.

    Body: same as /clean endpoint
    """
    body = await request.json()

    raw_home_data = body.get("home_data")
    if not raw_home_data:
        raise HTTPException(status_code=422, detail="缺少 home_data")

    bill_csv = None
    if body.get("bill_csv_base64"):
        try:
            raw = base64.b64decode(body["bill_csv_base64"])
            bill_csv = raw.decode("gb18030")
        except Exception:
            pass

    marketing_csv = None
    if body.get("marketing_csv_base64"):
        try:
            raw = base64.b64decode(body["marketing_csv_base64"])
            marketing_csv = raw.decode("gb18030")
        except Exception:
            pass

    reports = [
        process_shop_data(home_data, bill_csv, marketing_csv)
        for home_data in _normalize_home_data(raw_home_data)
    ]
    if not reports:
        raise HTTPException(status_code=422, detail="home_data 格式不正确")

    data_date = reports[0].get("数据日期", datetime.now().strftime("%Y-%m-%d"))
    filename = f"daily_report_{data_date}.json"

    content = json.dumps(reports, ensure_ascii=False, indent=2).encode("utf-8")

    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(content)),
        },
    )
