"""Cookie manager for handling browser authentication and cookies.

Provides async functions for:
- Creating anti-detection Chrome browsers
- Loading/saving cookies via Playwright storage_state
- Validating cookies by checking for login redirects
- QR code login flow with interactive prompts
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

from playwright.async_api import Browser, BrowserContext, Page, Playwright

from pdd_crawler import config

# Anti-detection browser arguments
_BROWSER_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-sandbox",
    "--disable-infobars",
    "--disable-dev-shm-usage",
    "--lang=zh-CN",
    "--disable-features=IsolateOrigins,site-per-process",
]

# User-agent must match Sec-CH-UA version below
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

# Client Hints headers — must match _USER_AGENT
_EXTRA_HEADERS = {
    "Sec-CH-UA": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
    "Sec-CH-UA-Mobile": "?0",
    "Sec-CH-UA-Platform": '"Windows"',
}

# Comprehensive anti-detection init script
_WEBDRIVER_OVERRIDE_SCRIPT = """
// 1. Remove webdriver flag
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

// 2. Chrome object mock
window.chrome = window.chrome || {};
window.chrome.runtime = window.chrome.runtime || {
    onMessage: { addListener: function(){}, removeListener: function(){} },
    sendMessage: function(){},
    connect: function() {
        return { onMessage: { addListener: function(){} }, postMessage: function(){} };
    },
    PlatformOs: { MAC: 'mac', WIN: 'win', ANDROID: 'android', CROS: 'cros', LINUX: 'linux', OPENBSD: 'openbsd' },
    PlatformArch: { ARM: 'arm', X86_32: 'x86-32', X86_64: 'x86-64', MIPS: 'mips', MIPS64: 'mips64' },
};
window.chrome.loadTimes = window.chrome.loadTimes || function() {
    return {
        requestTime: Date.now() / 1000,
        startLoadTime: Date.now() / 1000,
        commitLoadTime: Date.now() / 1000,
        finishDocumentLoadTime: Date.now() / 1000,
        finishLoadTime: Date.now() / 1000,
        firstPaintTime: Date.now() / 1000,
        firstPaintAfterLoadTime: 0,
        navigationType: 'Other',
        wasFetchedViaSpdy: false,
        wasNpnNegotiated: true,
        npnNegotiatedProtocol: 'h2',
        wasAlternateProtocolAvailable: false,
        connectionInfo: 'h2',
    };
};
window.chrome.csi = window.chrome.csi || function() {
    return { startE: Date.now(), onloadT: Date.now(), pageT: Date.now(), tran: 15 };
};

// 3. Realistic plugins mock
Object.defineProperty(navigator, 'plugins', {
    get: () => {
        const plugins = [
            { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer',
              description: 'Portable Document Format', length: 1,
              0: { type: 'application/x-google-chrome-pdf', suffixes: 'pdf',
                   description: 'Portable Document Format' } },
            { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai',
              description: '', length: 1,
              0: { type: 'application/pdf', suffixes: 'pdf', description: '' } },
            { name: 'Native Client', filename: 'internal-nacl-plugin',
              description: '', length: 2,
              0: { type: 'application/x-nacl', suffixes: '',
                   description: 'Native Client Executable' },
              1: { type: 'application/x-pnacl', suffixes: '',
                   description: 'Portable Native Client Executable' } },
        ];
        plugins.item = (i) => plugins[i];
        plugins.namedItem = (name) => plugins.find(p => p.name === name);
        plugins.refresh = () => {};
        return plugins;
    }
});

// 4. Languages
Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh', 'en'] });
Object.defineProperty(navigator, 'language', { get: () => 'zh-CN' });

// 5. Hardware fingerprint
Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
Object.defineProperty(navigator, 'maxTouchPoints', { get: () => 0 });
Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });

// 6. Remove Playwright / automation markers
delete window.__playwright;
delete window.__pw_manual;
delete window.__PW_inspect;

// 7. Override permissions query
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) =>
    parameters.name === 'notifications'
        ? Promise.resolve({ state: Notification.permission })
        : originalQuery(parameters);

// 8. WebGL vendor / renderer
try {
    const getParameter = WebGLRenderingContext.prototype.getParameter;
    WebGLRenderingContext.prototype.getParameter = function(parameter) {
        if (parameter === 37445) return 'Intel Inc.';
        if (parameter === 37446) return 'Intel Iris OpenGL Engine';
        return getParameter.call(this, parameter);
    };
} catch(e) {}

// 9. Prevent iframe contentWindow detection
try {
    const origGetOwnPropertyDescriptor = Object.getOwnPropertyDescriptor;
    Object.getOwnPropertyDescriptor = function(obj, prop) {
        if (prop === 'contentWindow') return undefined;
        return origGetOwnPropertyDescriptor.call(this, obj, prop);
    };
} catch(e) {}
"""

# PDD URLs
_PDD_HOME_URL = "https://mms.pinduoduo.com"
_PDD_LOGIN_INDICATOR = "/login"


async def create_browser(
    playwright: Playwright,
    headless: bool = True,
) -> Browser:
    """Launch Chrome browser with anti-detection arguments."""
    browser = await playwright.chromium.launch(
        channel="chrome",
        headless=headless,
        args=_BROWSER_ARGS,
    )
    return browser


async def create_context(browser: Browser) -> BrowserContext:
    """Create a new browser context with anti-detection settings."""
    context = await browser.new_context(
        user_agent=_USER_AGENT,
        viewport={"width": 1920, "height": 1080},
        locale="zh-CN",
        extra_http_headers=_EXTRA_HEADERS,
    )
    await context.add_init_script(_WEBDRIVER_OVERRIDE_SCRIPT)
    return context


async def load_cookies(
    playwright: Playwright,
    cookie_path: Path,
) -> Optional[tuple[BrowserContext, Browser]]:
    """Load cookies from a storage_state file.

    Returns:
        Tuple of (context, browser) or None if file doesn't exist.
    """
    cookie_path = Path(cookie_path)
    if not cookie_path.exists():
        print(f"[Cookie] 未找到 cookie 文件: {cookie_path}")
        return None

    browser = await create_browser(playwright, headless=True)
    context = await browser.new_context(
        storage_state=str(cookie_path),
        user_agent=_USER_AGENT,
        viewport={"width": 1920, "height": 1080},
        locale="zh-CN",
        extra_http_headers=_EXTRA_HEADERS,
    )
    await context.add_init_script(_WEBDRIVER_OVERRIDE_SCRIPT)
    print(f"[Cookie] 已加载 cookie: {cookie_path}")
    return context, browser


async def validate_cookies(page: Page, timeout: int = 15000) -> bool:
    """Validate cookies by checking for login redirect."""
    try:
        await page.goto(_PDD_HOME_URL, wait_until="domcontentloaded", timeout=timeout)
        await page.wait_for_timeout(3000)
    except Exception as e:
        print(f"[Cookie] 验证导航失败: {e}")
        return False

    current_url = page.url
    if _PDD_LOGIN_INDICATOR in current_url:
        print("[Cookie] Cookie 已失效，需要重新登录")
        return False

    print("[Cookie] Cookie 验证通过")
    return True


async def qr_login(
    playwright: Playwright,
    cookie_path: Path,
    timeout: int = 120,
) -> tuple[BrowserContext, Browser]:
    """Perform QR code login.

    Returns:
        Tuple of (context, browser).
    """
    cookie_path = Path(cookie_path)
    cookie_path.parent.mkdir(parents=True, exist_ok=True)

    browser = await create_browser(playwright, headless=False)
    context = await create_context(browser)
    page = await context.new_page()

    print("=" * 50)
    print("[登录] 正在打开拼多多商家后台登录页面...")
    print("[登录] 请使用拼多多 APP 扫描二维码登录")
    print(f"[登录] 超时时间: {timeout} 秒")
    print("=" * 50)

    await page.goto(
        _PDD_HOME_URL, wait_until="domcontentloaded", timeout=config.DEFAULT_TIMEOUT
    )

    elapsed = 0
    poll_interval = 2

    while elapsed < timeout:
        await asyncio.sleep(poll_interval)
        elapsed += poll_interval

        current_url = page.url
        if _PDD_LOGIN_INDICATOR not in current_url and _PDD_HOME_URL in current_url:
            print("[登录] 登录成功！正在保存 cookie...")
            await context.storage_state(path=str(cookie_path))
            print(f"[登录] Cookie 已保存至: {cookie_path}")
            return context, browser

        remaining = timeout - elapsed
        if remaining > 0 and remaining % 10 == 0:
            print(f"[登录] 等待扫码中... 剩余 {remaining} 秒")

    await context.close()
    await browser.close()
    raise TimeoutError(f"[登录] 扫码登录超时（{timeout}秒），请重试")


async def ensure_authenticated(
    playwright: Playwright,
    shop_name: Optional[str] = None,
) -> tuple[BrowserContext, Browser, str]:
    """Main entry point: ensure we have a valid authenticated session.

    Args:
        playwright: Playwright instance.
        shop_name: Shop name for cookie file naming. If None, will use default.

    Returns:
        Tuple of (context, browser, shop_name).
    """
    # If no shop_name provided, use default cookie path
    if shop_name is None:
        shop_name = "pdd_shop"

    cookie_path = config.get_cookie_path(shop_name)

    # Step 1: Try loading existing cookies
    result = await load_cookies(playwright, cookie_path)

    if result is not None:
        context, browser = result
        # Step 2: Validate loaded cookies
        page = await context.new_page()
        try:
            is_valid = await validate_cookies(page, timeout=15000)
        finally:
            await page.close()

        if is_valid:
            print(f"[Auth] 使用已有 cookie 认证成功 (店铺: {shop_name})")
            return context, browser, shop_name

        # Cookies invalid — close old context
        await context.close()
        await browser.close()
        print("[Auth] Cookie 已失效，切换到扫码登录")

    # Step 3: Fall back to QR login
    print("[Auth] 启动扫码登录流程...")
    context, browser = await qr_login(playwright, cookie_path, timeout=120)
    return context, browser, shop_name
