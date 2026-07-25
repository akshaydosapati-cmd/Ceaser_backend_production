from __future__ import annotations

from app.core.config.settings import settings
from app.intelligence.ai.llm.base import LLMProvider
from app.intelligence.ai.llm.router import AdaptiveLLMRouter


class LLMRegistry:
    def __init__(self) -> None:
        self.router = AdaptiveLLMRouter()

    def candidates(self, max_count: int = 2) -> list[tuple[str, LLMProvider]]:
        return [(name, provider) for name, provider in self.router.candidates(max_count=max_count)]

    def production(self) -> LLMProvider:
        candidates = self.candidates(max_count=1)
        if candidates:
            return candidates[0][1]
        return self.fallback()

    def fallback(self) -> LLMProvider:
        candidates = self.candidates(max_count=max(1, settings.llm_max_fallbacks + 1))
        if len(candidates) > 1:
            return candidates[1][1]
        raise RuntimeError("No LLM fallback provider is configured")

    @property
    def last_selected_provider_names(self) -> list[str]:
        return self.router.last_selected

    def health_snapshot(self) -> dict[str, dict[str, object]]:
        return self.router.snapshot()


llm_registry = LLMRegistry()
