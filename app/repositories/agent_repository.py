from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.agent import Agent, AgentModule


class AgentRepository:
    def __init__(self, db: Session):
        self.db = db

    def list(self, user_id: str | None = None) -> list[Agent]:
        query = self.db.query(Agent)
        if user_id:
            query = query.filter(Agent.user_id == user_id)
        return query.order_by(Agent.name.asc()).all()

    def get(self, agent_id: str) -> Agent | None:
        return self.db.get(Agent, agent_id)

    def create(self, user_id: str, name: str, enabled: bool = True) -> Agent:
        agent = Agent(user_id=user_id, name=name, enabled=enabled)
        self.db.add(agent)
        self.db.flush()
        return agent

    def add_module(self, agent_id: str, module_name: str, enabled: bool = True) -> AgentModule:
        module = AgentModule(agent_id=agent_id, module_name=module_name, enabled=enabled)
        self.db.add(module)
        self.db.flush()
        return module
