"""
拼多多店铺数据清洗程序
根据 template.md 规则，从各店铺文件夹提取数据并生成日报 JSON。
"""

import csv
import json
import os
import re
import sys
from datetime import datetime, timedelta
from glob import glob
from pathlib import Path

BASE_DIR = Path(__file__).parent

# ── 排除项（不计入费用统计）──────────────────────────────
EXCLUDED_DESCS = {
    "0010002|交易收入-订单收入",
    "0010005|交易收入-优惠券结算",
    "0020002|交易退款-订单退款",
    "0020005|交易退款-优惠券结算",
    "0070004|转账-广告账户",
    "0080001|提现-提现申请",
}


# ── 工具函数 ─────────────────────────────────────────────
def parse_yesterday_value(text: str) -> float:
    """从 '昨日 9292.51 ' 格式中提取数值"""
    m = re.search(r"昨日\s+([\d.]+)", text)
    return float(m.group(1)) if m else 0.0


def read_csv_rows(path: str) -> tuple[list[str], list[list[str]]]:
    """读取 GB18030 编码的 CSV，返回 (header, data_rows)，跳过前导说明行和尾部汇总行"""
    with open(path, "r", encoding="gb18030") as f:
        reader = csv.reader(f)
        rows = list(reader)

    # 找到表头行（含"商户订单号"）
    header_idx = None
    for i, row in enumerate(rows):
        if row and row[0] == "商户订单号":
            header_idx = i
            break
    if header_idx is None:
        return [], []

    header = rows[header_idx]
    data = [
        row for row in rows[header_idx + 1 :]
        if len(row) >= len(header) and not row[0].startswith("#")
        and any(cell.strip() for cell in row)  # 跳过纯空行，但保留商户订单号为空的有效数据行
    ]
    return header, data


def parse_amount(val: str) -> float:
    """安全解析金额字符串"""
    try:
        return float(val) if val else 0.0
    except ValueError:
        return 0.0


# ── 1. home_data 提取 ────────────────────────────────────
def find_yesterday_value(items: dict, label: str) -> float:
    """在 home_data items 中按语义查找'昨日'数值。

    不同店铺的 item 编号不固定，按内容匹配。
    查找策略：找到同时包含 label 和 "昨日 数值" 的最短 item，从中提取昨日值。
    例如 label="成交金额" 匹配 "成交金额3372.38趋势昨日 9097.97 " → 9097.97
    """
    candidates = []
    for key, val in items.items():
        if label in val and re.search(r"昨日\s+[\d.]+", val):
            candidates.append(val)
    if not candidates:
        return 0.0
    # 取最短的匹配项（最精确的那个）
    best = min(candidates, key=len)
    return parse_yesterday_value(best)


def extract_home_data(shop_dir: str) -> dict:
    """从 home_data JSON 提取成交金额和全站推广"""
    files = sorted(glob(os.path.join(shop_dir, "home_data_*.json")))
    if not files:
        return {"成交金额": 0.0, "全站推广": 0.0, "shop_name": "", "scraped_at": ""}

    # 取最新的文件
    with open(files[-1], "r", encoding="utf-8") as f:
        data = json.load(f)

    items = data.get("data", {})
    return {
        "成交金额": find_yesterday_value(items, "成交金额"),
        "全站推广": find_yesterday_value(items, "推广花费"),
        "shop_name": data.get("shop_name", ""),
        "scraped_at": data.get("scraped_at", ""),
    }


# ── 2. marketing（营销账户明细）提取 ─────────────────────
def extract_marketing(shop_dir: str, data_date: str) -> dict:
    """从营销账户明细提取 评价有礼 + 跨店满返（仅统计 data_date 当天的记录）"""
    files = sorted(glob(os.path.join(shop_dir, "pdd-mall-marketing-bill-detail*.csv")))
    if not files:
        return {"评价有礼": 0.0, "跨店满返": 0.0}

    _, rows = read_csv_rows(files[-1])
    pingjia = 0.0
    kuadian = 0.0

    # 营销账户 CSV 列序：商户订单号, 入账时间, 账务类型, 收入金额（+元）, 支出金额（-元）, 备注, 业务描述
    for row in rows:
        # 按入账时间过滤，只取 data_date 当天
        entry_time = row[1] if len(row) > 1 else ""
        if data_date and not entry_time.startswith(data_date):
            continue
        acct_type = row[2] if len(row) > 2 else ""
        expense = parse_amount(row[4]) if len(row) > 4 else 0.0
        if acct_type == "评价有礼":
            pingjia += abs(expense)
        elif acct_type == "跨店日常满返":
            kuadian += abs(expense)

    return {"评价有礼": pingjia, "跨店满返": kuadian}


# ── 3. bill（店铺账务明细）提取 ──────────────────────────
def extract_bill(shop_dir: str) -> dict:
    """从店铺账务明细提取技术服务费、售后费用、其他费用、平台返还"""
    files = sorted(glob(os.path.join(shop_dir, "pdd-mall-bill-detail*.csv")))
    if not files:
        return {"技术服务费": 0.0, "售后费用": 0.0, "其他费用": 0.0, "平台返还": 0.0}

    _, rows = read_csv_rows(files[-1])

    # bill CSV 列序：商户订单号, 发生时间, 收入金额（+元）, 支出金额（-元）, 账务类型, 备注, 业务描述
    service_fee = 0.0           # 技术服务费净额
    after_sales = 0.0           # 售后费用（支出绝对值）
    after_sales_income = 0.0    # 售后费用中的收入（维权返还等）
    other_expense = 0.0         # 其他费用
    return_fee = 0.0            # 平台返还

    for row in rows:
        if len(row) < 7:
            continue
        income = parse_amount(row[2])
        expense = parse_amount(row[3])
        acct_type = row[4]
        desc = row[6]

        # 跳过排除项
        if desc in EXCLUDED_DESCS:
            continue

        # ── 技术服务费 ──
        # 账务类型="技术服务费" → 0030002|技术服务费-基础技术服务费 的收入+支出
        if acct_type == "技术服务费" and desc == "0030002|技术服务费-基础技术服务费":
            service_fee += income + expense
            continue

        # 账务类型="其他" → 0030001|技术服务费-技术服务费 的收入+支出
        if acct_type == "其他" and desc == "0030001|技术服务费-技术服务费":
            service_fee += income + expense
            continue

        # ── 售后费用 ──
        # 所有业务描述以 0040 开头的行（售后费用类），不限账务类型
        # 包含：小额打款、售后补偿消费者、运费补偿、延迟发货、虚假发货、缺货等
        if desc.startswith("0040"):
            after_sales += abs(expense)
            if income > 0:
                after_sales_income += income
            continue

        # 账务类型="其他" → 业务描述含"售后"的支出（兜底匹配）
        if acct_type == "其他" and "售后" in desc and expense < 0:
            after_sales += abs(expense)
            continue

        # ── 平台返还 ──
        # 账务类型="其他"中所有收入金额（正值）之和
        if acct_type == "其他" and income > 0:
            return_fee += income
            continue

        # ── 其他费用 ──
        # 账务类型="其他"中，排除已归入技术服务费和售后费用的剩余支出
        if acct_type == "其他" and expense < 0:
            other_expense += abs(expense)
            continue

    return {
        "技术服务费": round(service_fee, 2),
        "售后费用": round(after_sales, 2),
        "其他费用": round(other_expense, 2),
        "平台返还": round(return_fee, 2),
    }


# ── 主流程 ───────────────────────────────────────────────
def process_shop(shop_dir: str) -> dict | None:
    """处理单个店铺文件夹，返回清洗后的数据字典"""
    shop_name = os.path.basename(shop_dir)

    home = extract_home_data(shop_dir)

    # 推断数据日期：采集日期的前一天（home_data 取的是"昨日"数据）
    scraped_at = home.get("scraped_at", "")
    if scraped_at:
        scraped_dt = datetime.fromisoformat(scraped_at)
        data_date = (scraped_dt - timedelta(days=1)).strftime("%Y-%m-%d")
        collect_date = scraped_dt.strftime("%Y-%m-%d")
    else:
        data_date = ""
        collect_date = ""

    marketing = extract_marketing(shop_dir, data_date)
    bill = extract_bill(shop_dir)

    return {
        "店铺名称": home.get("shop_name") or shop_name,
        "数据日期": data_date,
        "采集日期": collect_date,
        "成交金额": home["成交金额"],
        "全站推广": home["全站推广"],
        "评价有礼+跨店满返（营销账户导出）": round(marketing["评价有礼"] + marketing["跨店满返"], 2),
        "技术服务费（支出+返还净额）": bill["技术服务费"],
        "平台返还（维权）": bill["平台返还"],
        "售后费用（扣款中售后+其他中售后）": bill["售后费用"],
        "其他费用（排除技术服务费和售后后的剩余）": bill["其他费用"],
    }


def find_shop_dirs() -> list[str]:
    """扫描 BASE_DIR 下所有包含 home_data 或 pdd-mall-bill-detail 的子目录"""
    shops = []
    for entry in os.scandir(BASE_DIR):
        if not entry.is_dir():
            continue
        # 跳过 debug 等非店铺目录
        contents = os.listdir(entry.path)
        has_data = any(
            f.startswith("home_data_") or f.startswith("pdd-mall-bill-detail")
            for f in contents
        )
        if has_data:
            shops.append(entry.path)
    return sorted(shops)


def main():
    shops = find_shop_dirs()
    if not shops:
        print("未找到店铺数据目录", file=sys.stderr)
        sys.exit(1)

    results = []
    for shop_dir in shops:
        result = process_shop(shop_dir)
        if result:
            results.append(result)
            print(f"[OK] {result['店铺名称']}  数据日期={result['数据日期']}")

    if not results:
        print("无有效数据", file=sys.stderr)
        sys.exit(1)

    # 以数据日期命名输出文件
    data_date = results[0]["数据日期"]
    output_file = BASE_DIR / f"daily_report_{data_date}.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n输出: {output_file}")


if __name__ == "__main__":
    main()