from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.automation import Automation
from app.services.automations.automation_executor import AutomationExecutor
from app.services.automations.automation_time import next_run_at


class AutomationScheduler:
    def __init__(self, db: Session):
        self.db = db

    def calculate_next_run(self, automation: Automation) -> datetime | None:
        if automation.status != "active":
            return None
        return next_run_at(frequency=automation.trigger_frequency, trigger_time=automation.trigger_time, tz_name=automation.timezone)

    def due(self, user_id: str | None = None, limit: int | None = None) -> list[Automation]:
        now = datetime.now(timezone.utc)
        query = self.db.query(Automation).filter(Automation.status == "active", Automation.next_run_at.is_not(None), Automation.next_run_at <= now)
        if user_id:
            query = query.filter(Automation.user_id == user_id)
        query = query.order_by(Automation.next_run_at.asc())
        if limit:
            query = query.limit(limit)
        return query.all()

    def run_due(self, user_id: str | None = None, limit: int | None = None) -> list:
        executor = AutomationExecutor(self.db)
        return [executor.run(automation) for automation in self.due(user_id=user_id, limit=limit)]
