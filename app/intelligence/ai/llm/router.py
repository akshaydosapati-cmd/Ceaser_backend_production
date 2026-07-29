from __future__ import annotations

from dataclasses import dataclass, field
from time import monotonic
from typing import Any

from app.core.config.settings import settings
from app.intelligence.ai.errors import AIServiceUnavailableError
from app.intelligence.ai.llm.gemini_provider import GeminiFallbackProvider
from app.intelligence.ai.llm.groq_provider import GroqProvider
from app.intelligence.ai.llm.openai_provider import OpenAIProvider


@dataclass
class ProviderHealth:
    healthy: bool = True
    average_first_token_ms: float | None = None
    average_total_ms: float | None = None
    recent_error_rate: float = 0.0
    disabled_until: float | None = None
    consecutive_failures: int = 0
    successes: int = 0
    failures: int = 0
    last_error: str | None = None
    last_updated: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "healthy": self.healthy,
            "average_first_token_ms": self.average_first_token_ms,
            "average_total_ms": self.average_total_ms,
            "recent_error_rate": self.recent_error_rate,
            "disabled_until": self.disabled_until,
            "consecutive_failures": self.consecutive_failures,
            "successes": self.successes,
            "failures": self.failures,
            "last_error": self.last_error,
            "last_updated": self.last_updated,
        }


class AdaptiveLLMRouter:
    def __init__(self) -> None:
        # Hugging Face is intentionally excluded from production chat routing.
        # It may remain configured for other local experiments, but it must
        # never answer a CEASER chat or document-generation request.
        self._provider_names = [
            name.strip().lower()
            for name in settings.llm_provider_order_raw.split(",")
            if name.strip() and name.strip().lower() != "huggingface"
        ]
        self._factories = {
            "groq": GroqProvider,
            "gemini": GeminiFallbackProvider,
            "openai": OpenAIProvider,
        }
        self._health: dict[str, ProviderHealth] = {}
        self._last_selected: list[str] = []

    @property
    def last_selected(self) -> list[str]:
        return list(self._last_selected)

    def candidates(self, *, max_count: int = 2) -> list[tuple[str, Any]]:
        selected: list[tuple[str, Any]] = []
        for provider_name in self._provider_names:
            if len(selected) >= max_count:
                break
            provider = self._build_provider(provider_name)
            if provider is None:
                continue
            if not self._is_available(provider_name):
                continue
            selected.append((provider_name, provider))
        if not selected:
            for provider_name in self._provider_names:
                provider = self._build_provider(provider_name)
                if provider is not None:
                    selected.append((provider_name, provider))
                    break
        self._last_selected = [name for name, _ in selected]
        return selected[:max_count]

    def record_success(self, provider_name: str, *, total_ms: float, first_token_ms: float | None = None) -> None:
        health = self._state(provider_name)
        alpha = 0.2
        health.successes += 1
        health.consecutive_failures = 0
        health.healthy = True
        health.disabled_until = None
        health.last_error = None
        health.last_updated = monotonic()
        health.average_total_ms = total_ms if health.average_total_ms is None else (health.average_total_ms * (1 - alpha) + total_ms * alpha)
        if first_token_ms is not None:
            health.average_first_token_ms = first_token_ms if health.average_first_token_ms is None else (health.average_first_token_ms * (1 - alpha) + first_token_ms * alpha)
        total_attempts = health.successes + health.failures
        health.recent_error_rate = (health.failures / total_attempts) if total_attempts else 0.0

    def record_failure(self, provider_name: str, error: AIServiceUnavailableError) -> None:
        health = self._state(provider_name)
        health.failures += 1
        health.consecutive_failures += 1
        health.last_error = error.detail or error.category or error.__class__.__name__
        health.last_updated = monotonic()
        total_attempts = health.successes + health.failures
        health.recent_error_rate = (health.failures / total_attempts) if total_attempts else 1.0
        if error.retryable and health.consecutive_failures >= 2:
            health.disabled_until = monotonic() + settings.provider_circuit_breaker_seconds
            health.healthy = False
        elif not error.retryable:
            health.healthy = True

    def snapshot(self) -> dict[str, dict[str, Any]]:
        return {name: health.as_dict() for name, health in self._health.items()}

    def _build_provider(self, provider_name: str):
        factory = self._factories.get(provider_name)
        if not factory:
            return None
        if provider_name == "groq" and not settings.groq_api_key:
            return None
        if provider_name == "gemini" and not settings.gemini_api_key:
            return None
        if provider_name == "openai" and not settings.openai_api_key:
            return None
        return factory()

    def _is_available(self, provider_name: str) -> bool:
        health = self._health.get(provider_name)
        if not health or health.disabled_until is None:
            return True
        if monotonic() >= health.disabled_until:
            health.disabled_until = None
            health.consecutive_failures = 0
            health.healthy = True
            return True
        return False

    def _state(self, provider_name: str) -> ProviderHealth:
        if provider_name not in self._health:
            self._health[provider_name] = ProviderHealth()
        return self._health[provider_name]
