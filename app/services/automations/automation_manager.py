from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.automation import Automation, AutomationRun, AutomationTemplate
from app.services.audit_service import AuditService
from app.services.automations.automation_agent_router import AutomationAgentRouter
from app.services.automations.automation_executor import AutomationExecutor
from app.services.automations.automation_templates import AutomationTemplateRegistry
from app.services.automations.automation_time import next_run_at, normalize_timezone


class AutomationManager:
    def __init__(self, db: Session):
        self.db = db
        self.router = AutomationAgentRouter()
        self.templates = AutomationTemplateRegistry()

    def template_list(self) -> list[dict]:
        self._sync_templates()
        records = self.db.query(AutomationTemplate).filter(AutomationTemplate.is_active.is_(True)).order_by(AutomationTemplate.category.asc(), AutomationTemplate.name.asc()).all()
        return [
            {
                "id": record.id,
                "name": record.name,
                "category": record.category,
                "description": record.description,
                "default_agent": record.default_agent,
                "default_prompt": record.default_prompt,
                "supported_frequencies": record.supported_frequencies,
                "icon": record.icon,
                "is_active": record.is_active,
            }
            for record in records
        ]

    def list(self, user_id: str) -> list[Automation]:
        return self.db.query(Automation).filter(Automation.user_id == user_id).order_by(Automation.created_at.desc()).all()

    def get(self, automation_id: str, user_id: str) -> Automation | None:
        return self.db.query(Automation).filter(Automation.id == automation_id, Automation.user_id == user_id).first()

    def create(
        self,
        *,
        user_id: str,
        name: str,
        description: str | None,
        automation_type: str,
        trigger_frequency: str,
        trigger_time: str | None,
        timezone: str | None,
        status: str,
        config_json: dict | None = None,
        workspace_id: str | None = None,
    ) -> Automation:
        assigned_agent = self.router.route(automation_type)
        tz_name = normalize_timezone(timezone)
        automation = Automation(
            user_id=user_id,
            workspace_id=workspace_id,
            name=name,
            description=description,
            automation_type=automation_type.lower(),
            assigned_agent=assigned_agent,
            trigger_frequency=trigger_frequency.lower(),
            trigger_time=trigger_time,
            timezone=tz_name,
            status=status,
            config_json=config_json or {},
        )
        automation.next_run_at = next_run_at(frequency=automation.trigger_frequency, trigger_time=automation.trigger_time, tz_name=automation.timezone) if status == "active" else None
        self.db.add(automation)
        self.db.flush()
        AuditService(self.db).record(user_id=user_id, action="automation_created", resource_type="automation", resource_id=automation.id, metadata={"agent": assigned_agent}, commit=False)
        self.db.commit()
        self.db.refresh(automation)
        return automation

    def update(self, automation: Automation, **updates) -> Automation:
        for key in ["name", "description", "trigger_time", "workspace_id"]:
            if key in updates and updates[key] is not None:
                setattr(automation, key, updates[key])
        if updates.get("automation_type") is not None:
            automation.automation_type = updates["automation_type"].lower()
            automation.assigned_agent = self.router.route(automation.automation_type)
        if updates.get("trigger_frequency") is not None:
            automation.trigger_frequency = updates["trigger_frequency"].lower()
        if updates.get("timezone") is not None:
            automation.timezone = normalize_timezone(updates["timezone"])
        if updates.get("status") is not None:
            automation.status = updates["status"]
        if updates.get("config_json") is not None:
            automation.config_json = updates["config_json"]
        automation.next_run_at = next_run_at(frequency=automation.trigger_frequency, trigger_time=automation.trigger_time, tz_name=automation.timezone) if automation.status == "active" else None
        AuditService(self.db).record(user_id=automation.user_id, action="automation_updated", resource_type="automation", resource_id=automation.id, commit=False)
        self.db.commit()
        self.db.refresh(automation)
        return automation

    def pause(self, automation: Automation) -> Automation:
        automation.status = "paused"
        automation.next_run_at = None
        AuditService(self.db).record(user_id=automation.user_id, action="automation_paused", resource_type="automation", resource_id=automation.id, commit=False)
        self.db.commit()
        self.db.refresh(automation)
        return automation

    def resume(self, automation: Automation) -> Automation:
        automation.status = "active"
        automation.next_run_at = next_run_at(frequency=automation.trigger_frequency, trigger_time=automation.trigger_time, tz_name=automation.timezone)
        AuditService(self.db).record(user_id=automation.user_id, action="automation_resumed", resource_type="automation", resource_id=automation.id, commit=False)
        self.db.commit()
        self.db.refresh(automation)
        return automation

    def delete(self, automation: Automation) -> None:
        user_id = automation.user_id
        automation_id = automation.id
        self.db.delete(automation)
        AuditService(self.db).record(user_id=user_id, action="automation_deleted", resource_type="automation", resource_id=automation_id, commit=False)
        self.db.commit()

    def run_now(self, automation: Automation) -> AutomationRun:
        return AutomationExecutor(self.db).run(automation)

    def runs(self, automation: Automation) -> list[AutomationRun]:
        return self.db.query(AutomationRun).filter(AutomationRun.automation_id == automation.id, AutomationRun.user_id == automation.user_id).order_by(AutomationRun.started_at.desc()).all()

    def _sync_templates(self) -> None:
        changed = False
        existing = {template.id: template for template in self.db.query(AutomationTemplate).all()}
        for item in self.templates.list():
            record = existing.get(item["id"])
            if not record:
                self.db.add(AutomationTemplate(**item))
                changed = True
                continue
            for key, value in item.items():
                if getattr(record, key) != value:
                    setattr(record, key, value)
                    changed = True
        if changed:
            self.db.commit()
