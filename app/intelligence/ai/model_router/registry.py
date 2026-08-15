from __future__ import annotations

import logging

from app.core.config.settings import settings
from app.intelligence.ai.model_router.models import ModelDefinition, Workload


logger = logging.getLogger(__name__)


class ModelRegistry:
    def __init__(self, models: list[ModelDefinition] | None = None):
        self._models: dict[str, ModelDefinition] = {}
        for model in models if models is not None else configured_models():
            self.register(model)

    def register(self, model: ModelDefinition) -> None:
        if model.model_id in self._models:
            raise ValueError(f"Duplicate model ID: {model.model_id}")
        self._models[model.model_id] = model

    def get(self, model_id: str) -> ModelDefinition | None:
        return self._models.get(model_id)

    def enabled(self) -> list[ModelDefinition]:
        return [model for model in self._models.values() if model.enabled and model.available]

    def by_capability(self, capability: str) -> list[ModelDefinition]:
        return [model for model in self.enabled() if capability in model.capabilities]

    def by_provider(self, provider_id: str) -> list[ModelDefinition]:
        return [model for model in self.enabled() if model.provider_id == provider_id]

    def safe_metadata(self) -> list[dict]:
        return [model.safe_metadata() for model in self._models.values()]


def configured_models() -> list[ModelDefinition]:
    disabled = {item.strip() for item in settings.llm_disabled_models_raw.split(",") if item.strip()}
    order = [item.strip().lower() for item in settings.llm_provider_order_raw.split(",") if item.strip()]
    priorities = {provider: (len(order) - index) * 10 for index, provider in enumerate(order)}
    models = [
        ModelDefinition(
            model_id="openai-primary", provider_id="openai", provider_model_name=settings.openai_model,
            display_name="OpenAI Primary", enabled="openai-primary" not in disabled, available=bool(settings.openai_api_key),
            capabilities=frozenset({"general", "reasoning", "coding", "long_context", "creative", "structured_output"}),
            allowed_workloads=frozenset({Workload.NORMAL_CHAT, Workload.SPECIALIST, Workload.SOFTWARE_ENGINEERING}),
            context_window=128000, relative_speed=7, relative_quality=9, relative_cost=6, priority=priorities.get("openai", 0),
        ),
        ModelDefinition(
            model_id="nvidia-nemotron-3-ultra-550b-a55b", provider_id="nvidia",
            provider_model_name=settings.nvidia_model, display_name="NVIDIA Nemotron 3 Ultra 550B A55B",
            enabled="nvidia-nemotron-3-ultra-550b-a55b" not in disabled, available=bool(settings.nvidia_api_key),
            capabilities=frozenset({"general", "reasoning", "coding", "tool_use", "long_context"}),
            allowed_workloads=frozenset({Workload.SOFTWARE_ENGINEERING}),
            context_window=1000000, supports_tools=True, supports_streaming=True,
            relative_speed=2, relative_quality=10, relative_cost=4, priority=priorities.get("nvidia", 0) - 10,
            tags=("hosted_nim", "nemotron"),
            metadata={"endpoint_class": "nvidia_developer_hosted", "latency_class": "high"},
        ),
        ModelDefinition(
            model_id="groq-primary", provider_id="groq", provider_model_name=settings.groq_model,
            display_name="Groq Primary", enabled="groq-primary" not in disabled, available=bool(settings.groq_api_key),
            capabilities=frozenset({"general", "reasoning", "coding", "creative", "fast"}),
            allowed_workloads=frozenset({Workload.NORMAL_CHAT, Workload.SPECIALIST, Workload.SOFTWARE_ENGINEERING}),
            context_window=128000, relative_speed=10, relative_quality=8, relative_cost=2, priority=priorities.get("groq", 0),
        ),
        ModelDefinition(
            model_id="gemini-primary", provider_id="gemini", provider_model_name=settings.gemini_model,
            display_name="Gemini Primary", enabled="gemini-primary" not in disabled, available=bool(settings.gemini_api_key),
            capabilities=frozenset({"general", "reasoning", "long_context", "creative", "fast", "structured_output"}),
            allowed_workloads=frozenset({Workload.NORMAL_CHAT, Workload.SPECIALIST}),
            context_window=1000000, relative_speed=8, relative_quality=8, relative_cost=3, priority=priorities.get("gemini", 0),
        ),
        ModelDefinition(
            model_id="huggingface-primary", provider_id="huggingface", provider_model_name=settings.huggingface_model,
            display_name="Hugging Face Primary", enabled="huggingface-primary" not in disabled, available=bool(settings.huggingface_api_key),
            capabilities=frozenset({"coding", "reasoning", "long_context"}),
            allowed_workloads=frozenset({Workload.SOFTWARE_ENGINEERING}), context_window=32000,
            relative_speed=9, relative_quality=7, relative_cost=1, priority=priorities.get("huggingface", 0) + 10,
            metadata={"latency_class": "interactive"},
        ),
    ]
    for model in models:
        logger.info(
            "llm_model_config provider=%s model=%s credential_present=%s enabled=%s",
            model.provider_id, model.provider_model_name, model.available, model.enabled,
        )
    return models
