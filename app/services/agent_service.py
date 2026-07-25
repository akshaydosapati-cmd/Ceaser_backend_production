from __future__ import annotations

from threading import Lock

from sqlalchemy.orm import Session

from app.models.agent import Agent
from app.repositories.agent_repository import AgentRepository
from app.services.agent_registry import DEFAULT_AGENT_MODULES


_DEFAULT_AGENT_BOOTSTRAPPED: set[str] = set()
_DEFAULT_AGENT_BOOTSTRAP_LOCK = Lock()


class AgentService:
    def __init__(self, db: Session):
        self.db = db
        self.agents = AgentRepository(db)

    def list(self, user_id: str | None = None) -> list[Agent]:
        if user_id:
            self.ensure_default_agents(user_id)
        return self.agents.list(user_id=user_id)

    def get(self, agent_id: str) -> Agent | None:
        return self.agents.get(agent_id)

    def set_enabled(self, agent: Agent, enabled: bool) -> Agent:
        agent.enabled = enabled
        self.db.commit()
        self.db.refresh(agent)
        return agent

    def update_modules(self, agent: Agent, enabled_module_names: list[str] | None = None, enabled_module_ids: list[str] | None = None) -> Agent:
        if enabled_module_ids is not None:
            enabled_ids = set(enabled_module_ids)
            for module in agent.modules:
                module.enabled = module.id in enabled_ids
        elif enabled_module_names is not None:
            enabled_names = set(enabled_module_names)
            for module in agent.modules:
                module.enabled = module.module_name in enabled_names
        self.db.commit()
        self.db.refresh(agent)
        return agent

    def ensure_default_agents(self, user_id: str) -> None:
        with _DEFAULT_AGENT_BOOTSTRAP_LOCK:
            if user_id in _DEFAULT_AGENT_BOOTSTRAPPED:
                return
        existing = {agent.name for agent in self.agents.list(user_id=user_id)}
        changed = False
        for agent_name, module_names in DEFAULT_AGENT_MODULES.items():
            if agent_name in existing:
                continue
            agent = self.agents.create(user_id=user_id, name=agent_name, enabled=True)
            for module_name in module_names:
                self.agents.add_module(agent_id=agent.id, module_name=module_name, enabled=True)
            changed = True
        if changed:
            self.db.commit()
        with _DEFAULT_AGENT_BOOTSTRAP_LOCK:
            _DEFAULT_AGENT_BOOTSTRAPPED.add(user_id)
