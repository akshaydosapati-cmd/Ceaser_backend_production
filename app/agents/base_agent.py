from __future__ import annotations

from typing import Any

from app.agents.schemas import AgentContribution
from app.services.llm.mock_provider import MockProvider
from app.services.llm.provider import LLMProvider


class BaseAgent:
    name: str = ""
    domain: str = ""
    description: str = ""
    capabilities: list[str] = []
    frameworks: list[str] = []
    contribution_areas: list[str] = []

    def __init__(self, provider: LLMProvider | None = None):
        self.provider = provider or MockProvider()

    def analyze(self, context: dict[str, Any]) -> str:
        return self.provider.generate_response(
            message=context.get("message", ""),
            context={
                **context,
                "mode": "agent_analysis",
                "agent_profile": {
                    "name": self.name,
                    "domain": self.domain,
                    "description": self.description,
                    "capabilities": self.capabilities,
                    "frameworks": self.frameworks,
                },
            },
        )

    def contribute(self, context: dict[str, Any]) -> dict:
        analysis = self.analyze(context)
        contribution = AgentContribution(
            agent=self.name,
            domain=self.domain,
            analysis=analysis,
            recommendations=self._build_recommendations(context),
            frameworks_used=self.frameworks[:3],
            confidence=self._confidence(context),
        )
        return contribution.model_dump()

    def _build_recommendations(self, context: dict[str, Any]) -> list[str]:
        message = context.get("message", "")
        scope = context.get("scope", {}).get("type", "personal_ai_os")
        memory_count = len(context.get("memories", []))
        areas = self.contribution_areas[:3] or self.capabilities[:3]
        return [
            f"Apply {area} to '{message}' with CEASER context."
            for area in areas
        ] + [f"Use {memory_count} relevant memories to keep recommendations grounded in {scope}."]

    def _confidence(self, context: dict[str, Any]) -> float:
        memory_count = len(context.get("memories", []))
        project_count = len(context.get("projects", []))
        return min(0.95, 0.78 + (memory_count * 0.03) + (project_count * 0.02))
