"""Configuration and constants."""

from pathlib import Path

# Project directories
PROJECT_ROOT = Path(__file__).parent.parent.parent
COOKIES_DIR = PROJECT_ROOT / "cookies"
DOWNLOADS_DIR = PROJECT_ROOT / "downloads"
OUTPUT_DIR = PROJECT_ROOT / "output"
COOKIE_PATH = COOKIES_DIR / "pdd_cookies.json"

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

# Timeouts (in milliseconds, except QR_LOGIN_TIMEOUT which is in seconds)
QR_LOGIN_TIMEOUT = 120  # 2 minutes in seconds
PAGE_LOAD_TIMEOUT = 30000  # 30 seconds in milliseconds
DOWNLOAD_TIMEOUT = 60000  # 1 minute in milliseconds
COOKIE_VALIDATE_TIMEOUT = 15000  # 15 seconds in milliseconds
