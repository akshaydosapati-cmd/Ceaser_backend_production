from __future__ import annotations

from app.agents.alex.agent import AlexAgent
from app.agents.atlas.agent import AtlasAgent
from app.agents.base_agent import BaseAgent
from app.agents.bolt.agent import BoltAgent
from app.agents.friday.agent import FridayAgent
from app.agents.nova.agent import NovaAgent
from app.agents.zeus.agent import ZeusAgent
from app.services.llm.provider import LLMProvider


class AgentRegistry:
    def __init__(self, provider: LLMProvider | None = None):
        self.provider = provider
        self._agent_classes: dict[str, type[BaseAgent]] = {
            "Bolt": BoltAgent,
            "Alex": AlexAgent,
            "Friday": FridayAgent,
            "Zeus": ZeusAgent,
            "Nova": NovaAgent,
            "Atlas": AtlasAgent,
        }

    def get(self, name: str) -> BaseAgent | None:
        agent_class = self._agent_classes.get(name)
        if not agent_class:
            return None
        return agent_class(provider=self.provider)

    def load_many(self, names: list[str]) -> list[BaseAgent]:
        return [agent for name in names if (agent := self.get(name))]

    def names(self) -> list[str]:
        return list(self._agent_classes.keys())
