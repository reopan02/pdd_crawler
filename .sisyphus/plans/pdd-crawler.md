# PDD Merchant Backend Crawler (拼多多商家后台爬虫)

## TL;DR

> **Quick Summary**: Build a Python CLI tool using Playwright to scrape Pinduoduo merchant dashboard data and export bills from the cashier system, with persistent cookie management and QR-code login fallback.
> 
> **Deliverables**:
> - Python package `pdd_crawler` with CLI entry point
> - Cookie manager: persistent JSON storage, validation, QR login flow
> - Home scraper: extract all visible dashboard data to JSON
> - Bill exporter: trigger "导出账单" on 2 cashier tabs, download files
> 
> **Estimated Effort**: Medium
> **Parallel Execution**: YES - 4 waves
> **Critical Path**: Scaffolding → Cookie Manager → Home Scraper → Smoke Test

---

## Context

### Original Request
Build a Python crawler for Pinduoduo merchant backend:
1. Persist cookies in JSON, validate on startup
2. If cookie invalid → show QR login page for user to scan → update cookie
3. Scrape all data from `https://mms.pinduoduo.com/home/`
4. Export bills from `https://cashier.pinduoduo.com/main/bills?tab=4001&__app_code=113` using the page's "导出账单" feature
5. Export bills from `https://cashier.pinduoduo.com/main/bills?tab=4002&__app_code=113` using the page's "导出账单" feature

### Interview Summary
**Key Discussions**:
- Both target sites are React SPAs requiring JavaScript execution (React 16.14.0)
- Playwright (async Python) chosen over DrissionPage for better async support and community
- Cookie persistence via Playwright `storage_state` (JSON with cookies + localStorage)
- Greenfield project — empty directory `E:\code\crawler`

**Research Findings**:
- **dreammis/social-auto-upload**: Production pattern for `storage_state` cookie persistence across Chinese platforms — `browser.new_context(storage_state=file)` → check page elements → if login text appears → cookie expired
- **NanmiCoder/CrawlerTutorial**: Bilibili QR login pattern — navigate to login → display QR → poll for URL change → save state
- **PDD anti-content header**: PDD API requests include anti-bot `anti-content` token — browser automation avoids this entirely since SPA JS generates tokens naturally
- **Playwright download pattern**: `async with page.expect_download() as download_info: await click()` — must set up BEFORE clicking trigger

### Metis Review
**Identified Gaps** (addressed):
- "All data" scope is vague → Default: scrape all visible dashboard text/metrics as key-value pairs
- Bill export may be async (generate-then-download) → Plan handles both sync download and intermediate modals
- Cross-domain cookies (`mms.` vs `cashier.`) → Single browser context shares cookies on `.pinduoduo.com`
- QR code timeout → 120s timeout with clear abort message
- Windows path handling → Use `pathlib.Path` throughout
- PDD may detect Chromium → Use `channel="chrome"` (real Chrome) instead

---

## Work Objectives

### Core Objective
Create a Python CLI tool that automates PDD merchant backend data collection: cookie-authenticated dashboard scraping and bill file exports.

### Concrete Deliverables
- `src/pdd_crawler/` Python package with 4 modules + CLI entry point
- `cookies/pdd_state.json` — persistent cookie storage
- `output/home_data_{timestamp}.json` — scraped dashboard data
- `downloads/` — exported bill files from both cashier tabs

### Definition of Done
- [ ] `python -m pdd_crawler --help` shows usage with login/scrape/export/all options
- [ ] Cookie file saves/loads correctly in Playwright `storage_state` format
- [ ] Invalid cookie triggers headful QR login flow
- [ ] Home page scraper extracts visible dashboard data to JSON
- [ ] Bill exporter downloads files from both cashier tabs
- [ ] All smoke tests pass

### Must Have
- Playwright async Python with `channel="chrome"` (real Chrome browser)
- Cookie persistence via `storage_state` JSON file
- Cookie validation by navigating to home page and checking for login redirect
- QR login with 120-second timeout, clear console prompts
- Home data saved as JSON with timestamp filename
- Bill download via `page.expect_download()` pattern
- Single browser context for both domains
- `pathlib.Path` for all file operations (Windows compatibility)
- Basic anti-detection: `navigator.webdriver` override via `add_init_script`
- Graceful error handling with clear messages (no silent failures)

### Must NOT Have (Guardrails)
- No API reverse engineering — browser automation only, no direct API calls
- No `anti-content` token generation — let SPA's own JS handle it
- No `playwright-stealth` package — unreliable, use simple init script instead
- No multiple browser contexts — single context for both mms and cashier domains
- No auto-retry on login failures — could trigger account lockout
- No CAPTCHA solving — out of scope
- No database storage layer — JSON files only
- No web server/API layer — CLI tool only
- No scheduling/cron — one-shot execution
- No proxy rotation or IP management
- No multi-account management — single account, single cookie file
- No data transformation of downloaded bills — preserve original format
- No abstract base classes or factory patterns — simple, direct code
- No comprehensive docstrings everywhere — minimal inline comments only

---

## Verification Strategy

> **ZERO HUMAN INTERVENTION** — ALL verification is agent-executed. No exceptions.

### Test Decision
- **Infrastructure exists**: NO (greenfield)
- **Automated tests**: YES (tests-after) — smoke tests for imports and config
- **Framework**: pytest (lightweight, standard)

### QA Policy
Every task includes agent-executed QA scenarios.
Evidence saved to `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`.

- **CLI**: Use Bash — run commands, check exit codes, validate output
- **Module imports**: Use Bash (python -c) — import modules, verify no errors
- **File outputs**: Use Bash — check file existence, validate JSON, check file size

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Start Immediately — foundation):
└── Task 1: Project scaffolding + dependencies [quick]

Wave 2 (After Wave 1 — core modules, PARALLEL):
├── Task 2: Cookie manager module [unspecified-high]
└── Task 3: Config & CLI entry point [quick]

Wave 3 (After Wave 2 — feature modules, PARALLEL):
├── Task 4: Home page scraper module [unspecified-high]
└── Task 5: Bill exporter module [unspecified-high]

Wave 4 (After Wave 3 — verification):
└── Task 6: Integration & smoke test [quick]

Critical Path: Task 1 → Task 2 → Task 4 → Task 6
Parallel Speedup: ~35% faster than sequential (4 waves vs 6 serial tasks)
Max Concurrent: 2 (Waves 2 & 3)
```

### Dependency Matrix

| Task | Depends On | Blocks | Wave |
|------|-----------|--------|------|
| 1 | — | 2, 3 | 1 |
| 2 | 1 | 4, 5 | 2 |
| 3 | 1 | 4, 5 | 2 |
| 4 | 2, 3 | 6 | 3 |
| 5 | 2, 3 | 6 | 3 |
| 6 | 4, 5 | — | 4 |

### Agent Dispatch Summary

- **Wave 1**: 1 task — T1 → `quick`
- **Wave 2**: 2 tasks — T2 → `unspecified-high`, T3 → `quick`
- **Wave 3**: 2 tasks — T4 → `unspecified-high`, T5 → `unspecified-high`
- **Wave 4**: 1 task — T6 → `quick`

---

## TODOs

- [x] 1. Project Scaffolding & Dependencies

  **What to do**:
  - Create `pyproject.toml` with project metadata and dependencies: `playwright>=1.40`, `pytest>=7.0`
  - Create package structure: `src/pdd_crawler/__init__.py`, `__main__.py` (stub), `cookie_manager.py` (stub), `home_scraper.py` (stub), `bill_exporter.py` (stub), `config.py` (stub)
  - Create directories with `.gitkeep`: `cookies/`, `downloads/`, `output/`
  - Create `.gitignore` excluding: `cookies/*.json`, `downloads/*`, `output/*`, `__pycache__/`, `.venv/`, `*.pyc`, `qrcode.png`
  - Create `tests/__init__.py` (empty)
  - Each stub module should have a minimal docstring and `pass` — just enough to be importable
  - Run `pip install -e .` to install the package in development mode
  - Run `playwright install chromium chrome` to install browser binaries

  **Must NOT do**:
  - No actual implementation logic in stubs — only `pass` or minimal constants
  - No virtual environment creation — assume user has Python ready
  - No CI/CD configuration

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO (first task)
  - **Parallel Group**: Wave 1
  - **Blocks**: Tasks 2, 3
  - **Blocked By**: None

  **References**:

  **Pattern References**:
  - `dreammis/social-auto-upload` project structure — flat package with module-per-feature pattern

  **External References**:
  - Playwright Python install: `playwright install chromium chrome` installs both Chromium and Chrome channel
  - pyproject.toml format: PEP 621 standard project metadata

  **Acceptance Criteria**:

  ```
  Scenario: Project structure exists and is importable
    Tool: Bash
    Steps:
      1. Run: python -c "from pdd_crawler import cookie_manager, home_scraper, bill_exporter, config; print('ALL IMPORTS OK')"
      2. Run: python -m pdd_crawler 2>&1 || true
      3. Run: ls src/pdd_crawler/
      4. Run: ls cookies/ downloads/ output/ tests/
    Expected Result: Step 1 prints "ALL IMPORTS OK" with exit code 0. Step 3 shows 6 .py files. Step 4 shows .gitkeep in each dir.
    Evidence: .sisyphus/evidence/task-1-imports.txt
  ```

  **Commit**: YES
  - Message: `feat(scaffold): initialize pdd_crawler project structure`
  - Files: `pyproject.toml`, `src/pdd_crawler/*`, `.gitignore`, `cookies/.gitkeep`, `downloads/.gitkeep`, `output/.gitkeep`, `tests/__init__.py`

- [x] 2. Cookie Manager Module

  **What to do**:
  - Implement `src/pdd_crawler/cookie_manager.py` with these functions:

  - `async def create_browser(playwright, headless=True) -> tuple[Browser, BrowserContext]`:
    - Launch with `playwright.chromium.launch(headless=headless, channel="chrome", args=["--disable-blink-features=AutomationControlled", "--lang=zh-CN"])`
    - Create context, add init script: `Object.defineProperty(navigator, 'webdriver', { get: () => undefined })`
    - Return browser and context

  - `async def load_cookies(playwright, cookie_path: Path) -> tuple[Browser, BrowserContext] | None`:
    - If `cookie_path` doesn't exist, return None
    - Load via `browser.new_context(storage_state=str(cookie_path))`
    - Add webdriver override init script to context
    - Return browser and context

  - `async def validate_cookies(page: Page, timeout: int = 15000) -> bool`:
    - Navigate to `https://mms.pinduoduo.com/home/`
    - Wait up to `timeout` ms for page to settle
    - Check if current URL contains `/login` → return False (redirected to login = invalid)
    - Check if page has dashboard content (e.g., wait for any element that indicates logged-in state) → return True
    - On timeout or error → return False

  - `async def qr_login(playwright, cookie_path: Path, timeout: int = 120) -> tuple[Browser, BrowserContext]`:
    - Launch headful browser (`headless=False`) with `channel="chrome"`
    - Navigate to `https://mms.pinduoduo.com/login`
    - Print clear console message: "请使用拼多多商家APP扫描二维码登录（120秒超时）..."
    - Poll every 2 seconds: check if URL has changed away from `/login` (indicates successful login)
    - On success: save `context.storage_state(path=str(cookie_path))`, print "登录成功！Cookie已保存"
    - On timeout: raise `TimeoutError("QR login timed out after {timeout}s")`
    - Return browser and context (caller manages lifecycle)

  - `async def ensure_authenticated(playwright, cookie_path: Path) -> tuple[Browser, BrowserContext, Page]`:
    - Try `load_cookies()` → if loaded, create page, `validate_cookies()` → if valid, return
    - If no cookies or validation fails → call `qr_login()` → create page, return
    - This is the main entry point other modules use

  **Must NOT do**:
  - No auto-retry on QR login timeout — fail with clear error
  - No CAPTCHA detection/solving
  - No multiple browser contexts
  - No abstract base classes

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Task 3)
  - **Parallel Group**: Wave 2
  - **Blocks**: Tasks 4, 5
  - **Blocked By**: Task 1

  **References**:

  **Pattern References** (existing code to follow):
  - `dreammis/social-auto-upload/myUtils/auth.py` — Cookie validation pattern:
    ```python
    context = await browser.new_context(storage_state=account_file)
    page = await context.new_page()
    await page.goto(url)
    try:
        await page.get_by_text("扫码登录").wait_for(timeout=5000)
        return False  # cookie expired
    except:
        return True   # cookie valid
    ```
  - `dreammis/social-auto-upload/myUtils/login.py` — QR login flow:
    ```python
    page.on('framenavigated', lambda frame: asyncio.create_task(on_url_change()) if frame == page.main_frame else None)
    await asyncio.wait_for(url_changed_event.wait(), timeout=200)
    await context.storage_state(path=cookies_dir / f"{uuid_v1}.json")
    ```
  - `NanmiCoder/CrawlerTutorial/login/auth.py` — Cookie save/load utilities:
    ```python
    async def save_cookies_to_file(context, filepath):
        cookies = await context.cookies()
        with open(filepath, 'w') as f:
            json.dump(cookies, f, indent=2)
    async def load_cookies_from_file(context, filepath):
        with open(filepath, 'r') as f:
            cookies = json.load(f)
        await context.add_cookies(cookies)
    ```

  **External References**:
  - Playwright storage_state docs: `context.storage_state(path=...)` saves cookies + localStorage as JSON
  - Playwright browser launch: `channel="chrome"` uses installed Chrome instead of bundled Chromium

  **Acceptance Criteria**:

  ```
  Scenario: Cookie manager functions are importable and have correct signatures
    Tool: Bash
    Steps:
      1. Run: python -c "from pdd_crawler.cookie_manager import create_browser, load_cookies, validate_cookies, qr_login, ensure_authenticated; print('ALL FUNCTIONS OK')"
      2. Run: python -c "import inspect; from pdd_crawler.cookie_manager import validate_cookies; sig = inspect.signature(validate_cookies); print(sig); assert 'page' in sig.parameters"
    Expected Result: Step 1 prints "ALL FUNCTIONS OK". Step 2 shows (page, timeout=15000) signature.
    Evidence: .sisyphus/evidence/task-2-cookie-imports.txt

  Scenario: load_cookies returns None for missing file
    Tool: Bash
    Steps:
      1. Run: python -c "
         import asyncio
         from pathlib import Path
         from pdd_crawler.cookie_manager import load_cookies
         from playwright.async_api import async_playwright
         async def test():
             async with async_playwright() as p:
                 result = await load_cookies(p, Path('nonexistent_cookie.json'))
                 assert result is None, f'Expected None, got {result}'
                 print('PASS: returns None for missing file')
         asyncio.run(test())
         "
    Expected Result: Prints "PASS: returns None for missing file"
    Evidence: .sisyphus/evidence/task-2-cookie-missing.txt
  ```

  **Commit**: YES
  - Message: `feat(auth): add cookie manager with validation and QR login`
  - Files: `src/pdd_crawler/cookie_manager.py`

- [x] 3. Config & CLI Entry Point

  **What to do**:
  - Implement `src/pdd_crawler/config.py` with constants:
    ```python
    from pathlib import Path
    
    BASE_DIR = Path(__file__).resolve().parent.parent.parent  # project root
    COOKIE_PATH = BASE_DIR / "cookies" / "pdd_state.json"
    DOWNLOAD_DIR = BASE_DIR / "downloads"
    OUTPUT_DIR = BASE_DIR / "output"
    
    # URLs
    PDD_HOME_URL = "https://mms.pinduoduo.com/home/"
    PDD_LOGIN_URL = "https://mms.pinduoduo.com/login"
    CASHIER_BILL_4001_URL = "https://cashier.pinduoduo.com/main/bills?tab=4001&__app_code=113"
    CASHIER_BILL_4002_URL = "https://cashier.pinduoduo.com/main/bills?tab=4002&__app_code=113"
    
    # Timeouts
    QR_LOGIN_TIMEOUT = 120  # seconds
    PAGE_LOAD_TIMEOUT = 30000  # ms
    DOWNLOAD_TIMEOUT = 60000  # ms
    COOKIE_VALIDATE_TIMEOUT = 15000  # ms
    ```

  - Implement `src/pdd_crawler/__main__.py` with argparse CLI:
    ```
    usage: python -m pdd_crawler [--login] [--scrape-home] [--export-bills] [--all]
    
    --login         Force QR code login (refresh cookies)
    --scrape-home   Scrape dashboard data from home page
    --export-bills  Export bills from both cashier tabs
    --all           Run full flow: validate/login → scrape → export
    ```
    - Entry point creates async event loop with `asyncio.run(main())`
    - `main()` launches Playwright, calls `ensure_authenticated()` from cookie_manager
    - Routes to appropriate function based on args
    - Ensures browser cleanup in `finally` block
    - If no args provided, default to `--all`
    - Ensure `cookies/`, `downloads/`, `output/` dirs exist (mkdir with parents=True, exist_ok=True)

  **Must NOT do**:
  - No more than 4 CLI arguments
  - No config file loading (YAML/TOML) — constants in code are sufficient
  - No verbose/debug flags — keep it simple

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Task 2)
  - **Parallel Group**: Wave 2
  - **Blocks**: Tasks 4, 5
  - **Blocked By**: Task 1

  **References**:

  **Pattern References**:
  - `dreammis/social-auto-upload/conf.py` — Simple config with Path constants: `BASE_DIR = Path(__file__).parent`
  - Standard `__main__.py` pattern for Python packages

  **External References**:
  - Python argparse docs for mutually non-exclusive action flags
  - `asyncio.run()` as entry point for async main

  **Acceptance Criteria**:

  ```
  Scenario: CLI help text shows all options
    Tool: Bash
    Steps:
      1. Run: python -m pdd_crawler --help
    Expected Result: Output contains "--login", "--scrape-home", "--export-bills", "--all". Exit code 0.
    Evidence: .sisyphus/evidence/task-3-cli-help.txt

  Scenario: Config constants are correct URLs
    Tool: Bash
    Steps:
      1. Run: python -c "
         from pdd_crawler.config import PDD_HOME_URL, PDD_LOGIN_URL, CASHIER_BILL_4001_URL, CASHIER_BILL_4002_URL, COOKIE_PATH
         assert 'mms.pinduoduo.com/home' in PDD_HOME_URL
         assert 'mms.pinduoduo.com/login' in PDD_LOGIN_URL
         assert 'tab=4001' in CASHIER_BILL_4001_URL
         assert 'tab=4002' in CASHIER_BILL_4002_URL
         assert 'pdd_state.json' in str(COOKIE_PATH)
         print('ALL CONFIG OK')
         "
    Expected Result: Prints "ALL CONFIG OK" with exit code 0
    Evidence: .sisyphus/evidence/task-3-config-check.txt
  ```

  **Commit**: YES (groups with Task 2)
  - Message: `feat(cli): add config constants and CLI entry point`
  - Files: `src/pdd_crawler/config.py`, `src/pdd_crawler/__main__.py`

- [x] 4. Home Page Scraper Module

  **What to do**:
  - Implement `src/pdd_crawler/home_scraper.py` with:

  - `async def scrape_home(page: Page) -> dict`:
    - Navigate to `config.PDD_HOME_URL`
    - Wait for page to fully load — use `page.wait_for_load_state("networkidle")` with timeout from config
    - Additionally wait 3-5 seconds for SPA rendering (React async data loading)
    - Check if URL redirected to login → raise `RuntimeError("Session expired, please re-login")`
    - Extract ALL visible text/metrics from dashboard using multiple strategies:
      1. Try `page.query_selector_all('[class*="data"], [class*="card"], [class*="metric"], [class*="stat"], [class*="overview"], [class*="summary"]')` — find data containers by common class patterns
      2. Fallback: get all text content from main content area via `page.inner_text('body')` and structure it
    - Build result dict with:
      - `scraped_at`: ISO timestamp
      - `url`: current page URL
      - `page_title`: page title
      - `data`: dict of extracted key-value pairs or structured text sections
    - Return the dict

  - `async def save_home_data(data: dict, output_dir: Path) -> Path`:
    - Generate filename: `home_data_{timestamp}.json` (timestamp = `%Y%m%d_%H%M%S`)
    - Save to `output_dir / filename` as pretty-printed JSON (indent=2, ensure_ascii=False)
    - Print: `"首页数据已保存: {filepath}"`
    - Return the file path

  - `async def run_home_scraper(page: Page) -> Path`:
    - Orchestrator function: calls `scrape_home()` → `save_home_data()`
    - Returns output file path

  **Must NOT do**:
  - No spidering/crawling links found on the page
  - No intercepting network requests / API responses
  - No parsing beyond visible DOM content
  - No clicking into sub-pages or navigation items

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Task 5)
  - **Parallel Group**: Wave 3
  - **Blocks**: Task 6
  - **Blocked By**: Tasks 2, 3

  **References**:

  **Pattern References**:
  - Playwright `page.query_selector_all()` → iterate elements → `element.inner_text()`
  - `page.wait_for_load_state("networkidle")` ensures SPA data has loaded
  - JSON output with `json.dump(data, f, indent=2, ensure_ascii=False)` for Chinese text

  **External References**:
  - Playwright Page API: `query_selector_all`, `inner_text`, `wait_for_load_state`
  - PDD home page is a React SPA — dashboard has dynamic data widgets that load async

  **Acceptance Criteria**:

  ```
  Scenario: Home scraper functions are importable with correct signatures
    Tool: Bash
    Steps:
      1. Run: python -c "
         import inspect
         from pdd_crawler.home_scraper import scrape_home, save_home_data, run_home_scraper
         assert 'page' in inspect.signature(scrape_home).parameters
         assert 'data' in inspect.signature(save_home_data).parameters
         assert 'output_dir' in inspect.signature(save_home_data).parameters
         print('ALL HOME SCRAPER FUNCTIONS OK')
         "
    Expected Result: Prints "ALL HOME SCRAPER FUNCTIONS OK"
    Evidence: .sisyphus/evidence/task-4-home-imports.txt

  Scenario: save_home_data creates valid JSON file
    Tool: Bash
    Steps:
      1. Run: python -c "
         import asyncio, json
         from pathlib import Path
         from pdd_crawler.home_scraper import save_home_data
         from pdd_crawler.config import OUTPUT_DIR
         OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
         test_data = {'scraped_at': '2024-01-01T00:00:00', 'url': 'test', 'data': {'key': 'value', 'chinese': '测试数据'}}
         path = asyncio.run(save_home_data(test_data, OUTPUT_DIR))
         assert path.exists(), 'File not created'
         loaded = json.loads(path.read_text(encoding='utf-8'))
         assert loaded['data']['chinese'] == '测试数据', 'Chinese text not preserved'
         path.unlink()  # cleanup
         print('PASS: JSON output correct')
         "
    Expected Result: Prints "PASS: JSON output correct"
    Evidence: .sisyphus/evidence/task-4-home-save.txt
  ```

  **Commit**: YES (groups with Task 5)
  - Message: `feat(scraper): add home page data scraper`
  - Files: `src/pdd_crawler/home_scraper.py`

- [x] 5. Bill Exporter Module

  **What to do**:
  - Implement `src/pdd_crawler/bill_exporter.py` with:

  - `async def export_single_bill(page: Page, tab_url: str, download_dir: Path) -> Path | None`:
    - Navigate to `tab_url`
    - Wait for page load: `page.wait_for_load_state("networkidle")` + extra 3s wait for SPA
    - Check if URL redirected to login → raise `RuntimeError("Session expired")`
    - Locate export button — try these selectors in order:
      1. `page.get_by_text("导出账单")` (most reliable for Chinese text)
      2. `page.get_by_role("button", name="导出账单")`
      3. `page.locator('button:has-text("导出")')` (partial match fallback)
    - If button not found within 10s → print warning and return None
    - Ensure button is visible: `await button.scroll_into_view_if_needed()`
    - Handle potential confirmation modal:
      - Set up download expectation FIRST
      - Click the export button
      - If a modal/dialog appears (check for confirmation button within 3s), click confirm
    - Download handling:
      ```python
      async with page.expect_download(timeout=config.DOWNLOAD_TIMEOUT) as download_info:
          await button.click()
          # Handle intermediate modal if appears
          try:
              confirm = page.locator('button:has-text("确认"), button:has-text("确定"), button:has-text("导出")')
              await confirm.first.click(timeout=3000)
          except:
              pass  # No modal, download triggered directly
      download = await download_info.value
      filepath = download_dir / (download.suggested_filename or f"bill_{tab_url.split('tab=')[1][:4]}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
      await download.save_as(str(filepath))
      ```
    - Validate file size > 0, print `"账单已下载: {filepath}"`
    - Return filepath

  - `async def export_all_bills(page: Page, download_dir: Path) -> list[Path]`:
    - Call `export_single_bill(page, config.CASHIER_BILL_4001_URL, download_dir)`
    - Call `export_single_bill(page, config.CASHIER_BILL_4002_URL, download_dir)`
    - Return list of successfully downloaded file paths
    - Print summary: `"共下载 {N} 个账单文件"`

  **Must NOT do**:
  - No parsing/transforming downloaded bill content
  - No date range selection — use whatever the page defaults to
  - No retry on download failure — report error and continue to next tab
  - No multiple concurrent downloads

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Task 4)
  - **Parallel Group**: Wave 3
  - **Blocks**: Task 6
  - **Blocked By**: Tasks 2, 3

  **References**:

  **Pattern References**:
  - Playwright download pattern (from microsoft/playwright-python tests):
    ```python
    async with page.expect_download() as download_info:
        await page.click("download-trigger-selector")
    download = await download_info.value
    await download.save_as("/path/to/file")
    ```
  - `page.get_by_text()` for finding Chinese text buttons (from dreammis/social-auto-upload)
  - `scroll_into_view_if_needed()` before clicking (Metis edge case recommendation)

  **External References**:
  - Playwright Download API: `download.suggested_filename`, `download.save_as(path)`
  - Playwright `expect_download()` context manager must wrap the click that triggers it
  - PDD cashier page: "商家账房" React SPA at cashier.pinduoduo.com

  **Acceptance Criteria**:

  ```
  Scenario: Bill exporter functions are importable with correct signatures
    Tool: Bash
    Steps:
      1. Run: python -c "
         import inspect
         from pdd_crawler.bill_exporter import export_single_bill, export_all_bills
         sig1 = inspect.signature(export_single_bill)
         sig2 = inspect.signature(export_all_bills)
         assert 'page' in sig1.parameters
         assert 'tab_url' in sig1.parameters
         assert 'download_dir' in sig1.parameters
         assert 'page' in sig2.parameters
         print('ALL BILL EXPORTER FUNCTIONS OK')
         "
    Expected Result: Prints "ALL BILL EXPORTER FUNCTIONS OK"
    Evidence: .sisyphus/evidence/task-5-bill-imports.txt

  Scenario: Export uses correct URLs from config
    Tool: Bash
    Steps:
      1. Run: python -c "
         from pdd_crawler.config import CASHIER_BILL_4001_URL, CASHIER_BILL_4002_URL
         assert 'cashier.pinduoduo.com' in CASHIER_BILL_4001_URL
         assert 'tab=4001' in CASHIER_BILL_4001_URL
         assert 'tab=4002' in CASHIER_BILL_4002_URL
         print('BILL URLs CORRECT')
         "
    Expected Result: Prints "BILL URLs CORRECT"
    Evidence: .sisyphus/evidence/task-5-bill-urls.txt
  ```

  **Commit**: YES (groups with Task 4)
  - Message: `feat(export): add bill exporter with download handling`
  - Files: `src/pdd_crawler/bill_exporter.py`

- [x] 6. Integration & Smoke Test

  **What to do**:
  - Install Playwright browsers if not already: `playwright install chromium chrome`
  - Create `tests/test_smoke.py` with pytest tests:

  ```python
  # Test 1: All modules import without error
  def test_all_imports():
      from pdd_crawler import cookie_manager, home_scraper, bill_exporter, config

  # Test 2: Config constants are valid URLs
  def test_config_urls():
      from pdd_crawler.config import PDD_HOME_URL, PDD_LOGIN_URL, CASHIER_BILL_4001_URL, CASHIER_BILL_4002_URL
      assert "mms.pinduoduo.com" in PDD_HOME_URL
      assert "mms.pinduoduo.com" in PDD_LOGIN_URL
      assert "cashier.pinduoduo.com" in CASHIER_BILL_4001_URL
      assert "cashier.pinduoduo.com" in CASHIER_BILL_4002_URL
      assert "tab=4001" in CASHIER_BILL_4001_URL
      assert "tab=4002" in CASHIER_BILL_4002_URL

  # Test 3: Config paths use pathlib.Path
  def test_config_paths():
      from pdd_crawler.config import COOKIE_PATH, DOWNLOAD_DIR, OUTPUT_DIR
      from pathlib import Path
      assert isinstance(COOKIE_PATH, Path)
      assert isinstance(DOWNLOAD_DIR, Path)
      assert isinstance(OUTPUT_DIR, Path)

  # Test 4: Cookie manager returns None for missing file
  def test_load_cookies_missing_file():
      import asyncio
      from pathlib import Path
      from pdd_crawler.cookie_manager import load_cookies
      from playwright.async_api import async_playwright
      async def _test():
          async with async_playwright() as p:
              result = await load_cookies(p, Path("nonexistent_file.json"))
              assert result is None
      asyncio.run(_test())

  # Test 5: Home scraper save_home_data creates valid JSON
  def test_save_home_data():
      import asyncio, json
      from pathlib import Path
      from pdd_crawler.home_scraper import save_home_data
      import tempfile
      async def _test():
          with tempfile.TemporaryDirectory() as tmpdir:
              data = {"scraped_at": "2024-01-01", "data": {"test": "value"}}
              path = await save_home_data(data, Path(tmpdir))
              assert path.exists()
              loaded = json.loads(path.read_text(encoding="utf-8"))
              assert loaded["data"]["test"] == "value"
      asyncio.run(_test())

  # Test 6: CLI help works
  def test_cli_help(capsys):
      import subprocess
      result = subprocess.run(["python", "-m", "pdd_crawler", "--help"], capture_output=True, text=True)
      assert result.returncode == 0
      assert "--login" in result.stdout
      assert "--scrape-home" in result.stdout
      assert "--export-bills" in result.stdout
  ```

  - Run: `python -m pytest tests/test_smoke.py -v`
  - All 6 tests must pass
  - Fix any issues found during testing

  **Must NOT do**:
  - No tests that require live PDD authentication (those are manual integration tests)
  - No mocking of Playwright beyond what's needed

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO (depends on all previous tasks)
  - **Parallel Group**: Wave 4
  - **Blocks**: None
  - **Blocked By**: Tasks 4, 5

  **References**:

  **Pattern References**:
  - Standard pytest patterns with asyncio.run() for async test functions
  - subprocess.run for CLI integration tests

  **Acceptance Criteria**:

  ```
  Scenario: All smoke tests pass
    Tool: Bash
    Steps:
      1. Run: python -m pytest tests/test_smoke.py -v
    Expected Result: 6 tests pass, 0 failures. Exit code 0.
    Failure Indicators: Any "FAILED" in output, non-zero exit code
    Evidence: .sisyphus/evidence/task-6-smoke-tests.txt

  Scenario: Full CLI is functional
    Tool: Bash
    Steps:
      1. Run: python -m pdd_crawler --help
      2. Verify output contains all 4 options
    Expected Result: Help text shows --login, --scrape-home, --export-bills, --all
    Evidence: .sisyphus/evidence/task-6-cli-functional.txt
  ```

  **Commit**: YES
  - Message: `test(smoke): add integration smoke tests`
  - Files: `tests/test_smoke.py`

---

## Final Verification Wave

> After ALL implementation tasks, run verification.

- [ ] F1. **Smoke Test Verification** — `quick`
  Run `python -m pytest tests/test_smoke.py -v`. All tests must pass. Run `python -m pdd_crawler --help` and verify output shows all 4 options. Run `python -c "from pdd_crawler import cookie_manager, home_scraper, bill_exporter, config"` and verify no import errors.
  Output: `Tests [N/N pass] | CLI [PASS/FAIL] | Imports [PASS/FAIL] | VERDICT`

- [ ] F2. **Code Quality Review** — `quick`
  Check all `.py` files for: no `as any`/type-ignore equivalents, no empty except blocks (except intentional timeout catches), no print statements without context, no hardcoded absolute paths (must use config/pathlib), no unused imports. Verify `pyproject.toml` has correct dependencies.
  Output: `Files [N clean/N issues] | Dependencies [COMPLETE/MISSING] | VERDICT`

---

## Commit Strategy

- **Wave 1**: `feat(scaffold): initialize pdd_crawler project structure` — pyproject.toml, src/pdd_crawler/*, .gitignore
- **Wave 2**: `feat(auth): add cookie manager with QR login flow` — cookie_manager.py, config.py, __main__.py
- **Wave 3**: `feat(scraper): add home scraper and bill exporter modules` — home_scraper.py, bill_exporter.py
- **Wave 4**: `test(smoke): add integration smoke tests` — tests/test_smoke.py

---

## Success Criteria

### Verification Commands
```bash
python -m pdd_crawler --help  # Expected: usage with --login, --scrape-home, --export-bills, --all
python -c "from pdd_crawler import cookie_manager, home_scraper, bill_exporter"  # Expected: no errors
python -m pytest tests/test_smoke.py -v  # Expected: all tests pass
```

### Final Checklist
- [ ] All "Must Have" items present in code
- [ ] All "Must NOT Have" items absent from code
- [ ] All smoke tests pass
- [ ] Cookie file path uses pathlib.Path
- [ ] Single browser context for both domains
- [ ] QR login has 120s timeout
- [ ] Bill export uses expect_download() pattern
