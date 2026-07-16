from __future__ import annotations

from app.core.config.settings import settings
from app.intelligence.ai.llm.base import LLMProvider
from app.intelligence.ai.llm.gemini_provider import GeminiFallbackProvider
from app.intelligence.ai.llm.openai_provider import OpenAIProvider


class LLMRegistry:
    def production(self) -> LLMProvider:
        if settings.llm_provider.lower() == "gemini":
            return GeminiFallbackProvider()
        return OpenAIProvider()

    def fallback(self) -> LLMProvider:
        return GeminiFallbackProvider()


llm_registry = LLMRegistry()

