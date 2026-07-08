from __future__ import annotations

from dataclasses import dataclass

from app.core.config.settings import settings


@dataclass(frozen=True)
class LLMConfig:
    provider: str = settings.llm_provider
    model: str = settings.gemini_model
    temperature: float = settings.gemini_temperature
    max_tokens: int = settings.gemini_max_tokens


llm_config = LLMConfig()
