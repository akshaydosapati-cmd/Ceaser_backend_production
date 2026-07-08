from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.integration import Integration


AGENT_PROVIDER_ACCESS = {
    "Nova": ["google-calendar", "google-drive", "gmail"],
    "Alex": ["google-classroom", "google-tasks", "google-drive", "notion"],
    "Bolt": ["google-tasks", "google-calendar"],
    "Zeus": ["google-drive", "notion"],
    "Friday": ["google-calendar", "google-drive"],
    "Atlas": ["google-drive", "notion"],
}


class IntegrationContextService:
    def __init__(self, db: Session):
        self.db = db

    def for_agent(self, user_id: str, agent_name: str) -> dict:
        allowed = AGENT_PROVIDER_ACCESS.get(agent_name, [])
        records = self.db.query(Integration).filter(Integration.user_id == user_id, Integration.provider.in_(allowed), Integration.status == "connected").all()
        return {
            "agent": agent_name,
            "providers": [
                {
                    "provider": record.provider,
                    "account_email": record.provider_email,
                    "last_sync_at": record.last_sync_at.isoformat() if record.last_sync_at else None,
                    "metadata": record.metadata_json,
                }
                for record in records
            ],
        }

    def for_automation(self, user_id: str, automation_type: str) -> dict:
        agent = {
            "research": "Nova",
            "business": "Zeus",
            "content": "Friday",
            "learning": "Alex",
            "execution": "Bolt",
            "engineering": "Atlas",
        }.get(automation_type, "Bolt")
        return self.for_agent(user_id=user_id, agent_name=agent)
