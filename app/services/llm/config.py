from __future__ import annotations

from dataclasses import dataclass

from app.core.config.settings import settings


@dataclass(frozen=True)
class LLMConfig:
    provider: str = settings.llm_provider
    model: str = settings.openai_model
    temperature: float = settings.openai_temperature
    max_tokens: int = settings.openai_max_tokens


llm_config = LLMConfig()
