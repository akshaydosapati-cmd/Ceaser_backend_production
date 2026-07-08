from __future__ import annotations

from sqlalchemy.orm import Session

from app.repositories.agent_repository import AgentRepository
from app.services.agent_service import AgentService


class UserContextResolver:
    def __init__(self, db: Session):
        self.db = db
        self.agents = AgentRepository(db)

    def resolve(self, user_id: str) -> dict:
        AgentService(self.db).ensure_default_agents(user_id)
        enabled_agents = [
            {
                "id": agent.id,
                "name": agent.name,
                "enabled": agent.enabled,
                "modules": [module.module_name for module in agent.modules if module.enabled],
            }
            for agent in self.agents.list(user_id=user_id)
            if agent.enabled
        ]
        return {
            "scope": {
                "id": user_id,
                "name": "CEASER",
                "type": "personal_ai_os",
            },
            "enabled_agents": enabled_agents,
        }
