from __future__ import annotations
# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnusedCallResult=false

import asyncio
from collections.abc import Mapping
import json
import re
from dataclasses import dataclass
from pathlib import Path

from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig


ROOT = Path(__file__).resolve().parents[1]
COOKIES_DIR = ROOT / "cookies"
EVIDENCE_DIR = ROOT / ".sisyphus" / "evidence"

MMS_URL = "https://mms.pinduoduo.com"
CASHIER_URL = "https://cashier.pinduoduo.com/main/bills?tab=4001"
BLOCKED_KEYWORDS = ["登录异常", "关闭页面后重试", "访问异常", "验证身份"]


@dataclass
class AttemptResult:
    name: str
    browser_kwargs: Mapping[str, object]
    mms_success: bool
    mms_url: str
    mms_blocked_keywords: list[str]
    mms_snippet: str
    cashier_success: bool
    cashier_url: str
    cashier_blocked_keywords: list[str]
    cashier_snippet: str
    error: str | None = None


def _extract_text_snippet(html: str, max_len: int = 260) -> str:
    if not html:
        return ""
    text = re.sub(r"<script[\\s\\S]*?</script>", " ", html, flags=re.IGNORECASE)
    text = re.sub(r"<style[\\s\\S]*?</style>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\\s+", " ", text).strip()
    return text[:max_len]


def _find_keywords(text: str) -> list[str]:
    return [kw for kw in BLOCKED_KEYWORDS if kw in text]


def _pick_cookie_file() -> Path:
    candidates = sorted(COOKIES_DIR.glob("*_cookies.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates:
        raise FileNotFoundError(f"No *_cookies.json found in {COOKIES_DIR}")
    return candidates[0]


async def _run_attempt(
    name: str,
    cookie_file: Path,
    browser_kwargs: Mapping[str, object],
) -> AttemptResult:
    mms_url = ""
    cashier_url = ""
    mms_snippet = ""
    cashier_snippet = ""
    mms_blocked: list[str] = []
    cashier_blocked: list[str] = []
    try:
        cfg = BrowserConfig(
            headless=True,
            enable_stealth=True,
            storage_state=str(cookie_file),
            verbose=False,
            **browser_kwargs,
        )
        session_id = f"task1-{name}"
        async with AsyncWebCrawler(config=cfg) as crawler:
            mms = await crawler.arun(
                MMS_URL,
                config=CrawlerRunConfig(
                    session_id=session_id,
                    wait_until="domcontentloaded",
                    page_timeout=60000,
                    verbose=False,
                ),
            )
            mms_url = (getattr(mms, "redirected_url", None) or getattr(mms, "url", "") or "").strip()
            mms_snippet = _extract_text_snippet(getattr(mms, "html", "") or "")
            mms_blocked = _find_keywords(mms_snippet)
            mms_success = bool(getattr(mms, "success", False)) and "/login" not in mms_url.lower() and not mms_blocked

            cashier = await crawler.arun(
                MMS_URL,
                config=CrawlerRunConfig(
                    session_id=session_id,
                    js_code=f"window.location.href = '{CASHIER_URL}';",
                    wait_until="domcontentloaded",
                    wait_for_timeout=7000,
                    page_timeout=60000,
                    verbose=False,
                ),
            )
            cashier_url = (
                getattr(cashier, "redirected_url", None) or getattr(cashier, "url", "") or ""
            ).strip()
            cashier_snippet = _extract_text_snippet(getattr(cashier, "html", "") or "")
            cashier_blocked = _find_keywords(cashier_snippet)
            cashier_success = (
                bool(getattr(cashier, "success", False))
                and "/login" not in cashier_url.lower()
                and not cashier_blocked
            )

            return AttemptResult(
                name=name,
                browser_kwargs=browser_kwargs,
                mms_success=mms_success,
                mms_url=mms_url,
                mms_blocked_keywords=mms_blocked,
                mms_snippet=mms_snippet,
                cashier_success=cashier_success,
                cashier_url=cashier_url,
                cashier_blocked_keywords=cashier_blocked,
                cashier_snippet=cashier_snippet,
            )
    except Exception as exc:  # noqa: BLE001
        return AttemptResult(
            name=name,
            browser_kwargs=browser_kwargs,
            mms_success=False,
            mms_url=mms_url,
            mms_blocked_keywords=mms_blocked,
            mms_snippet=mms_snippet,
            cashier_success=False,
            cashier_url=cashier_url,
            cashier_blocked_keywords=cashier_blocked,
            cashier_snippet=cashier_snippet,
            error=f"{type(exc).__name__}: {exc}",
        )


def _render_attempt(attempt: AttemptResult) -> str:
    lines = [
        f"Attempt: {attempt.name}",
        f"Config: {json.dumps(attempt.browser_kwargs, ensure_ascii=False)}",
        f"MMS success: {attempt.mms_success}",
        f"MMS URL: {attempt.mms_url}",
        f"MMS blocked keywords: {attempt.mms_blocked_keywords}",
        f"MMS snippet: {attempt.mms_snippet}",
        f"Cashier success: {attempt.cashier_success}",
        f"Cashier URL: {attempt.cashier_url}",
        f"Cashier blocked keywords: {attempt.cashier_blocked_keywords}",
        f"Cashier snippet: {attempt.cashier_snippet}",
    ]
    if attempt.error:
        lines.append(f"Error: {attempt.error}")
    return "\n".join(lines)


def _write_evidence(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


async def main() -> int:
    cookie_file = _pick_cookie_file()
    attempts = [
        (
            "stealth-default",
            {
                "browser_type": "chromium",
                "viewport_width": 1920,
                "viewport_height": 1080,
            },
        ),
        (
            "stealth-extra-args",
            {
                "browser_type": "chromium",
                "viewport_width": 1920,
                "viewport_height": 1080,
                "extra_args": [
                    "--disable-blink-features=AutomationControlled",
                    "--lang=zh-CN",
                ],
            },
        ),
        (
            "stealth-extra-args-ua",
            {
                "browser_type": "chromium",
                "viewport_width": 1920,
                "viewport_height": 1080,
                "extra_args": [
                    "--disable-blink-features=AutomationControlled",
                    "--lang=zh-CN",
                    "--disable-features=IsolateOrigins,site-per-process",
                ],
                "user_agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"
                ),
                "headers": {
                    "Sec-CH-UA": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
                    "Sec-CH-UA-Mobile": "?0",
                    "Sec-CH-UA-Platform": '"Windows"',
                },
            },
        ),
    ]

    print(f"Using cookie file: {cookie_file}")

    results: list[AttemptResult] = []
    success = False
    for name, kwargs in attempts:
        print(f"\n===== Running attempt: {name} =====")
        result = await _run_attempt(name, cookie_file, kwargs)
        results.append(result)
        print(_render_attempt(result))
        if result.mms_success and result.cashier_success:
            success = True
            break

    pdd_report = [
        "Task 1 - PDD MMS access verification",
        f"Cookie file: {cookie_file}",
        "",
    ]
    cashier_report = [
        "Task 1 - PDD cashier anti-bot verification",
        f"Cookie file: {cookie_file}",
        "",
    ]

    for r in results:
        pdd_report.append(_render_attempt(r))
        pdd_report.append("")
        cashier_report.append(_render_attempt(r))
        cashier_report.append("")

    gate_line = "GATE VERDICT: PROCEED" if success else "GATE VERDICT: REEVALUATE"
    pdd_report.append(gate_line)
    cashier_report.append(gate_line)

    _write_evidence(EVIDENCE_DIR / "task-1-pdd-access.txt", "\n".join(pdd_report))
    _write_evidence(EVIDENCE_DIR / "task-1-cashier-access.txt", "\n".join(cashier_report))

    print(f"\n{gate_line}")
    return 0 if success else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    raise SystemExit(exit_code)
