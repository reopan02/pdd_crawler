"""Shared dependencies for web API modules.

Extracted to avoid circular imports between app.py and API routers.
"""

from __future__ import annotations

from fastapi import Request

from pdd_crawler.chrome_pool import ChromePool

# Global Chrome pool singleton — initialized in app.py lifespan
chrome_pool = ChromePool()


def get_session_id(request: Request) -> str:
    """Extract session ID from header or query param."""
    sid = request.headers.get("X-Session-ID")
    if not sid:
        sid = request.query_params.get("session_id")
    if not sid:
        sid = "default"
    return sid
