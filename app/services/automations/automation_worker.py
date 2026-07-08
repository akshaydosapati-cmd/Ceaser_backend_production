from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.core.config.settings import settings
from app.core.database.session import SessionLocal
from app.services.automations.automation_scheduler import AutomationScheduler

logger = logging.getLogger(__name__)


@dataclass
class AutomationWorkerState:
    enabled: bool = False
    running: bool = False
    interval_seconds: int = 60
    batch_size: int = 10
    started_at: datetime | None = None
    last_scan_at: datetime | None = None
    last_run_count: int = 0
    total_runs: int = 0
    last_error: str | None = None
    task: asyncio.Task | None = field(default=None, repr=False)

    def as_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "running": self.running,
            "interval_seconds": self.interval_seconds,
            "batch_size": self.batch_size,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "last_scan_at": self.last_scan_at.isoformat() if self.last_scan_at else None,
            "last_run_count": self.last_run_count,
            "total_runs": self.total_runs,
            "last_error": self.last_error,
        }


class AutomationWorker:
    def __init__(self) -> None:
        self.state = AutomationWorkerState(
            enabled=settings.automation_worker_enabled,
            interval_seconds=max(settings.automation_worker_interval_seconds, 5),
            batch_size=max(settings.automation_worker_batch_size, 1),
        )

    def start(self) -> None:
        if not self.state.enabled or self.state.task:
            return
        self.state.running = True
        self.state.started_at = datetime.now(timezone.utc)
        self.state.task = asyncio.create_task(self._loop(), name="ceaser-automation-worker")
        logger.info("CEASER automation worker started.")

    async def stop(self) -> None:
        self.state.running = False
        task = self.state.task
        if not task:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        self.state.task = None
        logger.info("CEASER automation worker stopped.")

    async def _loop(self) -> None:
        while self.state.running:
            await self.scan_once()
            await asyncio.sleep(self.state.interval_seconds)

    async def scan_once(self) -> int:
        return await asyncio.to_thread(self._scan_once_sync)

    def _scan_once_sync(self) -> int:
        self.state.last_scan_at = datetime.now(timezone.utc)
        try:
            with SessionLocal() as db:
                runs = AutomationScheduler(db).run_due(limit=self.state.batch_size)
                self.state.last_run_count = len(runs)
                self.state.total_runs += len(runs)
                self.state.last_error = None
                return len(runs)
        except Exception as exc:
            self.state.last_run_count = 0
            self.state.last_error = str(exc)
            logger.exception("Automation worker scan failed.")
            return 0


automation_worker = AutomationWorker()
