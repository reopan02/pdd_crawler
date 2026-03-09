"""Configuration and constants."""

from pathlib import Path

# Project directories
PROJECT_ROOT = Path(__file__).parent.parent.parent
COOKIES_DIR = PROJECT_ROOT / "cookies"

# Output directory - all outputs (scraped data + downloaded bills) go here
# Structure: output/{shop_name}/
OUTPUT_BASE_DIR = PROJECT_ROOT / "output"


def get_cookie_path(shop_name: str) -> Path:
    """Get cookie file path for a specific shop.

    Args:
        shop_name: Sanitized shop name.

    Returns:
        Path to the cookie JSON file.
    """
    return COOKIES_DIR / f"{shop_name}_cookies.json"


def get_shop_output_dir(shop_name: str) -> Path:
    """Get output directory for a specific shop.

    Args:
        shop_name: Sanitized shop name.

    Returns:
        Path to the shop's output directory.
    """
    return OUTPUT_BASE_DIR / shop_name


# Default configuration
DEFAULT_TIMEOUT = 30000
DEFAULT_HEADLESS = False

# PDD URLs
PDD_HOME_URL = "https://mms.pinduoduo.com/home/"
PDD_LOGIN_URL = "https://mms.pinduoduo.com/login"

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

# Timeouts (in milliseconds, except QR_LOGIN_TIMEOUT which is in seconds)
QR_LOGIN_TIMEOUT = 120  # 2 minutes in seconds
PAGE_LOAD_TIMEOUT = 30000  # 30 seconds in milliseconds
DOWNLOAD_TIMEOUT = 60000  # 1 minute in milliseconds
COOKIE_VALIDATE_TIMEOUT = 15000  # 15 seconds in milliseconds
