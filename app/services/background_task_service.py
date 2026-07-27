from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Lock
from typing import Any


@dataclass
class BackgroundTaskRecord:
    id: str
    user_id: str
    status: str = "queued"
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class BackgroundTaskStore:
    def __init__(self) -> None:
        self._tasks: dict[str, BackgroundTaskRecord] = {}
        self._lock = Lock()

    def create(self, task_id: str, user_id: str) -> BackgroundTaskRecord:
        with self._lock:
            record = BackgroundTaskRecord(id=task_id, user_id=user_id)
            self._tasks[task_id] = record
            return record

    def set_running(self, task_id: str) -> None:
        self._update(task_id, status="running")

    def set_result(self, task_id: str, result: dict[str, Any]) -> None:
        self._update(task_id, status="completed", result=result)

    def set_error(self, task_id: str, error: str) -> None:
        self._update(task_id, status="failed", error=error)

    def get(self, task_id: str) -> BackgroundTaskRecord | None:
        with self._lock:
            return self._tasks.get(task_id)

    def _update(self, task_id: str, **updates: Any) -> None:
        with self._lock:
            record = self._tasks.get(task_id)
            if not record:
                return
            for key, value in updates.items():
                setattr(record, key, value)
            record.updated_at = datetime.now(timezone.utc).isoformat()


background_task_store = BackgroundTaskStore()
