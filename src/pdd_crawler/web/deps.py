"""Shared dependencies for web API modules.

Extracted to avoid circular imports between app.py and API routers.
"""

from __future__ import annotations

import asyncio

from fastapi import Request

# Browser pool semaphore — max 2 concurrent browser contexts
browser_semaphore = asyncio.Semaphore(2)


def get_session_id(request: Request) -> str:
    """Extract session ID from header or query param."""
    sid = request.headers.get("X-Session-ID")
    if not sid:
        sid = request.query_params.get("session_id")
    if not sid:
        sid = "default"
    return sid
