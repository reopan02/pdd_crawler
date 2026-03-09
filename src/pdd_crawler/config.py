"""Configuration and constants."""

from pathlib import Path

# Project directories
PROJECT_ROOT = Path(__file__).parent.parent.parent
COOKIES_DIR = PROJECT_ROOT / "cookies"
DOWNLOADS_DIR = PROJECT_ROOT / "downloads"
OUTPUT_DIR = PROJECT_ROOT / "output"

# Default configuration
DEFAULT_TIMEOUT = 30000
DEFAULT_HEADLESS = False

# PDD URLs
PDD_HOME_URL = "https://pdd.fsps.ru/"
PDD_LOGIN_URL = "https://pdd.fsps.ru/login"

# Cashier Bill URLs
CASHIER_BILL_4001_URL = "https://pdd.fsps.ru/cashier/bill/4001"
CASHIER_BILL_4002_URL = "https://pdd.fsps.ru/cashier/bill/4002"

# Timeouts (in milliseconds, except QR_LOGIN_TIMEOUT which is in seconds)
QR_LOGIN_TIMEOUT = 300  # 5 minutes in seconds
PAGE_LOAD_TIMEOUT = 60000  # 60 seconds in milliseconds
DOWNLOAD_TIMEOUT = 120000  # 2 minutes in milliseconds
COOKIE_VALIDATE_TIMEOUT = 30000  # 30 seconds in milliseconds
