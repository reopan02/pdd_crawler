"""Configuration and constants."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# Project directories
PROJECT_ROOT = Path(__file__).parent.parent.parent

# Data directory (SQLite, etc.)
DATA_DIR = PROJECT_ROOT / "data"

# ── Chrome Container Endpoints ────────────────────────────
# Each shop gets a dedicated Chrome container with CDP + VNC.
# First login is done manually via VNC; subsequent operations use CDP.


@dataclass
class ChromeEndpoint:
    """A single Chrome container endpoint."""

    shop_id: str  # unique identifier, e.g. "shop1"
    shop_name: str  # display name, e.g. "路驼ROAD CAMEL八伍叁专卖店"
    cdp_url: str  # e.g. "http://localhost:9222"
    vnc_url: str  # e.g. "http://localhost:6080" (noVNC web client)


# Static configuration — add/remove shops here.
# Override via environment: CHROME_SHOP1_CDP=http://host:9222 etc.
CHROME_ENDPOINTS: list[ChromeEndpoint] = [
    ChromeEndpoint(
        shop_id="shop1",
        shop_name="店铺1",
        cdp_url=os.environ.get("CHROME_SHOP1_CDP", "http://localhost:9222"),
        vnc_url=os.environ.get("CHROME_SHOP1_VNC", "http://localhost:6080"),
    ),
    # Add more shops:
    # ChromeEndpoint(
    #     shop_id="shop2",
    #     shop_name="店铺2",
    #     cdp_url=os.environ.get("CHROME_SHOP2_CDP", "http://localhost:9223"),
    #     vnc_url=os.environ.get("CHROME_SHOP2_VNC", "http://localhost:6081"),
    # ),
]


def get_endpoint(shop_id: str) -> ChromeEndpoint | None:
    """Look up a Chrome endpoint by shop_id."""
    for ep in CHROME_ENDPOINTS:
        if ep.shop_id == shop_id:
            return ep
    return None


def add_endpoint(ep: ChromeEndpoint) -> None:
    """Dynamically add a shop endpoint (idempotent — replaces if exists)."""
    remove_endpoint(ep.shop_id)
    CHROME_ENDPOINTS.append(ep)


def remove_endpoint(shop_id: str) -> bool:
    """Remove a shop endpoint by shop_id. Returns True if found."""
    for i, ep in enumerate(CHROME_ENDPOINTS):
        if ep.shop_id == shop_id:
            CHROME_ENDPOINTS.pop(i)
            return True
    return False


# ── PDD URLs ──────────────────────────────────────────────
PDD_HOME_URL = "https://mms.pinduoduo.com/home/"
PDD_LOGIN_URL = "https://mms.pinduoduo.com/login"
CASHIER_HOME_URL = "https://cashier.pinduoduo.com/"

# MMS proxy URL for cashier — navigating here triggers SSO ticket flow
# (mms generates auth ticket → redirects to cashier.pinduoduo.com/main/auth?ticket=...)
MMS_CASHIER_PROXY_URL = "https://mms.pinduoduo.com/cashier/finance/payment-bills"

# Cashier Bill URLs
CASHIER_BILL_4001_URL = (
    "https://cashier.pinduoduo.com/main/bills?tab=4001&__app_code=113"
)
CASHIER_BILL_4002_URL = (
    "https://cashier.pinduoduo.com/main/bills?tab=4002&__app_code=113"
)

# Export history pages (where generated bill files are downloaded from)
CASHIER_EXPORT_HISTORY_4001_URL = (
    "https://cashier.pinduoduo.com/main/bills/export-history?tab=4001&__app_code=113"
)
CASHIER_EXPORT_HISTORY_4002_URL = (
    "https://cashier.pinduoduo.com/main/bills/export-history?tab=4002&__app_code=113"
)

# Map bill tab → export history page
BILL_EXPORT_HISTORY_MAP = {
    CASHIER_BILL_4001_URL: CASHIER_EXPORT_HISTORY_4001_URL,
    CASHIER_BILL_4002_URL: CASHIER_EXPORT_HISTORY_4002_URL,
}

# ── Timeouts ──────────────────────────────────────────────
QR_LOGIN_TIMEOUT = 120  # seconds — VNC login polling timeout
PAGE_LOAD_TIMEOUT = 30000  # ms
DOWNLOAD_TIMEOUT = 60000  # ms
CDP_CONNECT_TIMEOUT = 10000  # ms

# Navigation retry settings
NAV_MAX_RETRIES = 3
NAV_RETRY_BASE_DELAY = 3.0  # seconds, doubles each retry

# Blocked text patterns indicating page/login errors
BLOCKED_TEXTS = ["登录异常", "关闭页面后重试", "访问异常", "验证身份"]

# Sidebar navigation — candidate text labels to click (tried in order)
SIDEBAR_TEXTS = ["对账中心", "账房", "账单"]

# Debug screenshot directory name (created under output_dir)
DEBUG_SCREENSHOT_DIR = "debug"

# Login detection polling interval (seconds)
LOGIN_POLL_INTERVAL = 3
