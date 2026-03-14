"""Configuration and constants."""

from pathlib import Path

# Project directories
PROJECT_ROOT = Path(__file__).parent.parent.parent

# Legacy paths — kept for cookie_manager.py backward compatibility
# but no longer used for persistent storage. All data is in-memory.
COOKIES_DIR = PROJECT_ROOT / "cookies"


def get_cookie_path(shop_name: str) -> Path:
    """Get cookie file path for a specific shop (legacy, used by cookie_manager)."""
    return COOKIES_DIR / f"{shop_name}_cookies.json"


# Default configuration
DEFAULT_TIMEOUT = 30000
DEFAULT_HEADLESS = False

# PDD URLs
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

# Timeouts (in milliseconds, except QR_LOGIN_TIMEOUT which is in seconds)
QR_LOGIN_TIMEOUT = 120  # 2 minutes in seconds
PAGE_LOAD_TIMEOUT = 30000  # 30 seconds in milliseconds
DOWNLOAD_TIMEOUT = 60000  # 1 minute in milliseconds
COOKIE_VALIDATE_TIMEOUT = 15000  # 15 seconds in milliseconds

# Browser configuration for crawl4ai
BROWSER_CONFIG = {
    "browser_type": "chromium",
    "headless": True,
    "enable_stealth": True,
    "viewport_width": 1920,
    "viewport_height": 1080,
    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "extra_args": [
        "--disable-blink-features=AutomationControlled",
        "--no-sandbox",
        "--disable-infobars",
        "--disable-dev-shm-usage",
        "--lang=zh-CN",
        "--disable-features=IsolateOrigins,site-per-process",
    ],
}

# Anti-bot detection scripts - executed before each page load
STEALTH_SCRIPTS = [
    # Remove navigator.webdriver property
    """() => {
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined,
            configurable: true
        });
    }""",
    # Mock Chrome runtime
    """() => {
        window.chrome = window.chrome || {
            runtime: {
                connect: function() {},
                sendMessage: function() {}
            }
        };
    }""",
    # Override permissions query
    """() => {
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications' ?
                Promise.resolve({ state: Notification.permission }) :
                originalQuery(parameters)
        );
    }""",
    # Mock plugins
    """() => {
        Object.defineProperty(navigator, 'plugins', {
            get: () => [1, 2, 3, 4, 5],
            configurable: true
        });
        Object.defineProperty(navigator, 'languages', {
            get: () => ['zh-CN', 'zh', 'en'],
            configurable: true
        });
    }""",
]

# Extra headers for HTTP requests
EXTRA_HEADERS = {
    "Sec-CH-UA": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
    "Sec-CH-UA-Mobile": "?0",
    "Sec-CH-UA-Platform": '"Windows"',
}

# Blocked text patterns indicating page/login errors
BLOCKED_TEXTS = ["登录异常", "关闭页面后重试", "访问异常", "验证身份"]

# Sidebar navigation — candidate text labels to click (tried in order)
SIDEBAR_TEXTS = ["对账中心", "账房", "账单"]

# Navigation retry settings
NAV_MAX_RETRIES = 3
NAV_RETRY_BASE_DELAY = 3.0  # seconds, doubles each retry (exponential backoff)

# Debug screenshot directory name (created under output_dir)
DEBUG_SCREENSHOT_DIR = "debug"

# Enable file downloads
ACCEPT_DOWNLOADS = True
