from __future__ import annotations

from collections.abc import Callable
from time import monotonic, perf_counter
from typing import Any

from app.core.config.settings import settings
from app.intelligence.ai.errors import AIServiceUnavailableError
from app.intelligence.ai.model_router.models import FailureCategory, HealthState, ModelEvent, ModelRequest, ModelResponse, RoutingPolicy, SelectedModel
from app.intelligence.ai.model_router.registry import ModelRegistry


class ModelRouter:
    def __init__(self, registry: ModelRegistry | None = None, provider_factories: dict[str, Callable[[], Any]] | None = None):
        self.registry = registry or ModelRegistry()
        self.provider_factories = provider_factories or self._default_provider_factories()
        self._health: dict[str, dict[str, Any]] = {}
        self.events: list[ModelEvent] = []
        self._last_selected: list[str] = []

    @property
    def last_selected(self) -> list[str]:
        return list(self._last_selected)

    def selections(self, request: ModelRequest, *, max_count: int | None = None, exclude: set[str] | None = None) -> list[SelectedModel]:
        self._event("model.route_requested", request, {"required_capabilities": sorted(request.required_capabilities), "policy": request.policy.value, "workload": request.workload.value})
        excluded = exclude or set()
        eligible = [model for model in self.registry.enabled() if model.model_id not in excluded and self._eligible(model, request)]
        ranked = sorted((SelectedModel(request_id=request.request_id, model=model, score=self._score(model, request), reason=self._reason(model, request)) for model in eligible), key=lambda item: (-item.score, -item.model.priority, item.model.model_id))
        selected = ranked[:max_count] if max_count is not None else ranked
        self._last_selected = [item.model.provider_id for item in selected]
        if selected:
            self._event("model.selected", request, {"model_id": selected[0].model.model_id, "provider_id": selected[0].model.provider_id, "score": selected[0].score})
        return selected

    def candidates(self, *, max_count: int = 2, request: ModelRequest | None = None) -> list[tuple[str, Any]]:
        from app.intelligence.ai.model_router.request_builder import request_for_chat
        selected = self.selections(request or request_for_chat(), max_count=max_count)
        return [(item.model.provider_id, self.provider_factories[item.model.provider_id]()) for item in selected if item.model.provider_id in self.provider_factories]

    def model_candidates(self, request: ModelRequest, *, max_count: int) -> list[tuple[SelectedModel, Any]]:
        return [(item, self.provider_factories[item.model.provider_id]()) for item in self.selections(request, max_count=max_count) if item.model.provider_id in self.provider_factories]

    async def generate(self, request: ModelRequest, *, instructions: str, input_text: str, max_output_tokens: int | None = None) -> ModelResponse:
        attempts = self.model_candidates(request, max_count=max(1, settings.llm_max_fallbacks + 1))
        last_error: AIServiceUnavailableError | None = None
        history: list[dict[str, Any]] = []
        for index, (selection, provider) in enumerate(attempts):
            started = perf_counter()
            self._event("model.attempt_started", request, {"model_id": selection.model.model_id, "attempt": index + 1})
            try:
                content = await provider.generate(instructions=instructions, input_text=input_text, model=selection.model.provider_model_name, max_output_tokens=max_output_tokens)
                latency = (perf_counter() - started) * 1000
                self.record_success(selection.model.provider_id, total_ms=latency, model_id=selection.model.model_id)
                self._event("model.completed", request, {"model_id": selection.model.model_id, "attempt": index + 1, "latency_ms": round(latency, 2)})
                return ModelResponse(content=content, provider_id=selection.model.provider_id, model_id=selection.model.model_id, latency_ms=latency, fallback_used=index > 0, attempt_count=index + 1, routing_metadata={"attempts": history, "reason": selection.reason})
            except Exception as error:  # provider adapters normalize their own errors
                normalized = error if isinstance(error, AIServiceUnavailableError) else AIServiceUnavailableError(type(error).__name__, provider=selection.model.provider_id, category="unknown")
                last_error = normalized
                category = self.classify_failure(normalized)
                self.record_failure(selection.model.provider_id, normalized, model_id=selection.model.model_id)
                history.append({"model_id": selection.model.model_id, "provider_id": selection.model.provider_id, "category": category.value})
                self._event("model.attempt_failed", request, history[-1] | {"attempt": index + 1})
                if not normalized.retryable or category == FailureCategory.AUTHENTICATION:
                    break
                if index + 1 < len(attempts):
                    self._event("model.fallback", request, {"from_model_id": selection.model.model_id, "attempt": index + 2})
        raise last_error or AIServiceUnavailableError("No eligible model is configured.", retryable=False, category="model_unavailable")

    def record_success(self, provider_name: str, *, total_ms: float, first_token_ms: float | None = None, model_id: str | None = None) -> None:
        for key in self._health_keys(provider_name, model_id):
            state = self._state(key)
            state.update(state=HealthState.HEALTHY, failures=0, cooldown_until=None, last_error=None, total_ms=total_ms, first_token_ms=first_token_ms)

    def record_failure(self, provider_name: str, error: AIServiceUnavailableError, *, model_id: str | None = None) -> None:
        category = self.classify_failure(error)
        for key in self._health_keys(provider_name, model_id):
            state = self._state(key)
            state["failures"] += 1
            state["last_error"] = category.value
            if category in {FailureCategory.RATE_LIMIT, FailureCategory.TIMEOUT, FailureCategory.PROVIDER_UNAVAILABLE, FailureCategory.NETWORK_ERROR}:
                state["state"] = HealthState.COOLDOWN
                state["cooldown_until"] = monotonic() + settings.provider_circuit_breaker_seconds
            elif category == FailureCategory.AUTHENTICATION:
                state["state"] = HealthState.UNAVAILABLE

    def snapshot(self) -> dict[str, dict[str, Any]]:
        return {key: {**value, "state": value["state"].value} for key, value in self._health.items()}

    @staticmethod
    def classify_failure(error: AIServiceUnavailableError) -> FailureCategory:
        category = str(error.category or "").lower()
        aliases = {"configuration": FailureCategory.AUTHENTICATION, "auth": FailureCategory.AUTHENTICATION, "provider_error": FailureCategory.PROVIDER_UNAVAILABLE, "dns": FailureCategory.NETWORK_ERROR, "network": FailureCategory.NETWORK_ERROR}
        try:
            return FailureCategory(category)
        except ValueError:
            return aliases.get(category, FailureCategory.UNKNOWN)

    def _eligible(self, model, request: ModelRequest) -> bool:
        if request.workload not in model.allowed_workloads: return False
        if not request.required_capabilities.issubset(model.capabilities): return False
        if request.needs_tools and not model.supports_tools: return False
        if request.needs_vision and not model.supports_vision: return False
        if request.needs_streaming and not model.supports_streaming: return False
        if request.context_size_estimate > model.context_window: return False
        state = self._health.get(model.model_id) or self._health.get(model.provider_id)
        if state and state["state"] == HealthState.UNAVAILABLE: return False
        if state and state["state"] == HealthState.COOLDOWN and monotonic() < (state["cooldown_until"] or 0): return False
        if state and state["state"] == HealthState.COOLDOWN: state.update(state=HealthState.DEGRADED, cooldown_until=None)
        return True

    @staticmethod
    def _score(model, request: ModelRequest) -> float:
        preferred = len(request.preferred_capabilities.intersection(model.capabilities)) * 12
        primary = 50 if request.workload.value == "normal_chat" and model.provider_id == settings.llm_provider.strip().lower() else 0
        # Purpose-configured coding models should lead software work. General
        # providers remain eligible as fallbacks when those models are down.
        workload_fit = 60 if request.workload.value == "software_engineering" and model.allowed_workloads == {request.workload} else 0
        if request.policy == RoutingPolicy.FAST: policy = model.relative_speed * 4 + model.relative_quality + (11 - model.relative_cost)
        elif request.policy == RoutingPolicy.QUALITY: policy = model.relative_quality * 4 + model.relative_speed + (11 - model.relative_cost)
        elif request.policy == RoutingPolicy.ECONOMY: policy = (11 - model.relative_cost) * 4 + model.relative_quality + model.relative_speed
        else: policy = model.relative_quality * 2 + model.relative_speed * 2 + (11 - model.relative_cost) * 2
        return float(100 + preferred + policy + model.priority + primary + workload_fit)

    @staticmethod
    def _reason(model, request: ModelRequest) -> str:
        preferred = sorted(request.preferred_capabilities.intersection(model.capabilities))
        return f"workload:{request.workload.value};required:{','.join(sorted(request.required_capabilities))};preferred:{','.join(preferred)};policy:{request.policy.value};health:eligible"

    def _state(self, key: str) -> dict[str, Any]:
        return self._health.setdefault(key, {"state": HealthState.UNKNOWN, "failures": 0, "cooldown_until": None, "last_error": None, "total_ms": None, "first_token_ms": None})

    @staticmethod
    def _health_keys(provider: str, model_id: str | None) -> list[str]:
        return [provider] if not model_id else [provider, model_id]

    def _event(self, name: str, request: ModelRequest, metadata: dict[str, Any]) -> None:
        safe = {key: value for key, value in metadata.items() if "key" not in key.lower() and "secret" not in key.lower() and "token" not in key.lower()}
        self.events.append(ModelEvent(event=name, request_id=request.request_id, metadata={"agent_id": request.agent_id, "task_type": request.task_type, **safe}))

    @staticmethod
    def _default_provider_factories() -> dict[str, Callable[[], Any]]:
        from app.intelligence.ai.llm.gemini_provider import GeminiFallbackProvider
        from app.intelligence.ai.llm.groq_provider import GroqProvider
        from app.intelligence.ai.llm.huggingface_provider import HuggingFaceProvider
        from app.intelligence.ai.llm.nvidia_provider import NvidiaProvider
        from app.intelligence.ai.llm.openai_provider import OpenAIProvider

        return {
            "openai": OpenAIProvider, "groq": GroqProvider,
            "gemini": GeminiFallbackProvider, "huggingface": HuggingFaceProvider,
            "nvidia": NvidiaProvider,
        }
