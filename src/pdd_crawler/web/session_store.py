"""Session store — tasks and logs only.

Shops are managed by config.py (static endpoints) and chrome_pool.py (connections).
This store handles crawl tasks, progress logs, and SSE streaming state.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class LogEntry:
    """A single log line with timestamp."""

    ts: float
    msg: str


class LogBuffer:
    """Append-only log buffer with cursor-based reading for SSE streaming."""

    def __init__(self) -> None:
        self._lines: list[LogEntry] = []
        self.finished: bool = False

    def append(self, msg: str) -> None:
        self._lines.append(LogEntry(ts=time.time(), msg=msg))

    def read_since(self, cursor: int) -> tuple[list[LogEntry], int]:
        """Return (new_entries, new_cursor) since the given cursor position."""
        new = self._lines[cursor:]
        return new, len(self._lines)


@dataclass
class TaskResult:
    """Result of a crawl/export task."""

    task_id: str
    task_type: str  # scrape_home | export_bills | full | qr_login
    status: str = "pending"  # pending | running | completed | failed
    progress: int = 0  # 0-100
    message: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    files: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    log: LogBuffer = field(default_factory=LogBuffer)


@dataclass
class Session:
    """Per-user session state."""

    session_id: str
    tasks: dict[str, TaskResult] = field(default_factory=dict)
    log_buffers: dict[str, LogBuffer] = field(default_factory=dict)


class SessionStore:
    """In-memory session store for tasks and logs."""

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}

    def get_or_create(self, session_id: str) -> Session:
        if session_id not in self._sessions:
            self._sessions[session_id] = Session(session_id=session_id)
        return self._sessions[session_id]

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

    def get_or_create_log(self, session_id: str, name: str) -> LogBuffer:
        session = self.get_or_create(session_id)
        if name not in session.log_buffers:
            session.log_buffers[name] = LogBuffer()
        return session.log_buffers[name]

    def get_log(self, session_id: str, name: str) -> LogBuffer | None:
        session = self._sessions.get(session_id)
        if session is None:
            return None
        return session.log_buffers.get(name)


# Global singleton
store = SessionStore()
