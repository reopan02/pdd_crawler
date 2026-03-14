"""In-memory session store for multi-user isolation.

Each session (identified by X-Session-ID header or query param) has its own
cookie store, task list, and crawl results. Data is lost on server restart.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CookieEntry:
    """A single uploaded/logged-in cookie."""

    cookie_id: str
    shop_name: str
    storage_state: dict  # Playwright storage_state JSON
    status: str = "unknown"  # unknown | valid | invalid | validating


@dataclass
class TaskResult:
    """Result of a crawl/export task."""

    task_id: str
    task_type: str  # scrape_home | export_bills | full
    status: str = "pending"  # pending | running | completed | failed
    progress: int = 0  # 0-100
    message: str = ""
    data: dict[str, Any] = field(default_factory=dict)  # scraped data
    files: list[dict[str, Any]] = field(default_factory=list)  # downloaded file bytes
    error: str | None = None


@dataclass
class Session:
    """Per-user session state."""

    session_id: str
    cookies: dict[str, CookieEntry] = field(default_factory=dict)
    tasks: dict[str, TaskResult] = field(default_factory=dict)


class SessionStore:
    """Thread-safe in-memory session store."""

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}

    def get_or_create(self, session_id: str) -> Session:
        if session_id not in self._sessions:
            self._sessions[session_id] = Session(session_id=session_id)
        return self._sessions[session_id]

    def get(self, session_id: str) -> Session | None:
        return self._sessions.get(session_id)

    def add_cookie(
        self, session_id: str, shop_name: str, storage_state: dict
    ) -> CookieEntry:
        session = self.get_or_create(session_id)
        cookie_id = str(uuid.uuid4())[:8]
        entry = CookieEntry(
            cookie_id=cookie_id,
            shop_name=shop_name,
            storage_state=storage_state,
        )
        session.cookies[cookie_id] = entry
        return entry

    def get_cookie(self, session_id: str, cookie_id: str) -> CookieEntry | None:
        session = self._sessions.get(session_id)
        if session is None:
            return None
        return session.cookies.get(cookie_id)

    def remove_cookie(self, session_id: str, cookie_id: str) -> bool:
        session = self._sessions.get(session_id)
        if session is None:
            return False
        return session.cookies.pop(cookie_id, None) is not None

    def list_cookies(self, session_id: str) -> list[CookieEntry]:
        session = self._sessions.get(session_id)
        if session is None:
            return []
        return list(session.cookies.values())

    def create_task(self, session_id: str, task_type: str) -> TaskResult:
        session = self.get_or_create(session_id)
        task_id = str(uuid.uuid4())[:8]
        task = TaskResult(task_id=task_id, task_type=task_type)
        session.tasks[task_id] = task
        return task

    def get_task(self, session_id: str, task_id: str) -> TaskResult | None:
        session = self._sessions.get(session_id)
        if session is None:
            return None
        return session.tasks.get(task_id)

    def list_tasks(self, session_id: str) -> list[TaskResult]:
        session = self._sessions.get(session_id)
        if session is None:
            return []
        return list(session.tasks.values())


# Global singleton
store = SessionStore()
