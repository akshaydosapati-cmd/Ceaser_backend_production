from __future__ import annotations

import logging
import re

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
            model_id="openai-primary",
            provider_id="openai",
            provider_model_name=settings.openai_model,
            display_name="OpenAI Primary",
            enabled="openai-primary" not in disabled,
            available=bool(settings.openai_api_key),
            capabilities=frozenset({"general", "reasoning", "coding", "long_context", "creative", "structured_output"}),
            allowed_workloads=frozenset({Workload.NORMAL_CHAT, Workload.SPECIALIST, Workload.SOFTWARE_ENGINEERING}),
            context_window=128000,
            relative_speed=7,
            relative_quality=9,
            relative_cost=6,
            priority=priorities.get("openai", 0),
        ),
        ModelDefinition(
            model_id="nvidia-nemotron-3-ultra-550b-a55b",
            provider_id="nvidia",
            provider_model_name=settings.nvidia_model,
            display_name="NVIDIA Nemotron 3 Ultra 550B A55B",
            enabled="nvidia-nemotron-3-ultra-550b-a55b" not in disabled,
            available=bool(settings.nvidia_api_key),
            capabilities=frozenset({"general", "reasoning", "coding", "tool_use", "long_context"}),
            allowed_workloads=frozenset({Workload.SOFTWARE_ENGINEERING}),
            context_window=1000000,
            supports_tools=True,
            supports_streaming=True,
            relative_speed=2,
            relative_quality=10,
            relative_cost=4,
            priority=priorities.get("nvidia", 0) - 10,
            tags=("hosted_nim", "nemotron"),
            metadata={"endpoint_class": "nvidia_developer_hosted", "latency_class": "high"},
        ),
        ModelDefinition(
            model_id="groq-primary",
            provider_id="groq",
            provider_model_name=settings.groq_model,
            display_name="Groq Primary",
            enabled="groq-primary" not in disabled,
            available=bool(settings.groq_api_key),
            capabilities=frozenset({"general", "reasoning", "coding", "creative", "fast"}),
            allowed_workloads=frozenset({Workload.NORMAL_CHAT, Workload.SPECIALIST, Workload.SOFTWARE_ENGINEERING}),
            context_window=128000,
            relative_speed=10,
            relative_quality=8,
            relative_cost=2,
            priority=priorities.get("groq", 0),
        ),
        ModelDefinition(
            model_id="gemini-primary",
            provider_id="gemini",
            provider_model_name=settings.gemini_model,
            display_name="Gemini Primary",
            enabled="gemini-primary" not in disabled,
            available=bool(settings.gemini_api_key),
            capabilities=frozenset({"general", "reasoning", "long_context", "creative", "fast", "structured_output"}),
            allowed_workloads=frozenset({Workload.NORMAL_CHAT, Workload.SPECIALIST}),
            context_window=1000000,
            relative_speed=8,
            relative_quality=8,
            relative_cost=3,
            priority=priorities.get("gemini", 0),
        ),
        *configured_huggingface_models(disabled, priorities),
    ]
    for model in models:
        logger.info(
            "llm_model_config provider=%s model=%s credential_present=%s enabled=%s",
            model.provider_id,
            model.provider_model_name,
            model.available,
            model.enabled,
        )
    return models


def configured_huggingface_models(disabled: set[str], priorities: dict[str, int]) -> list[ModelDefinition]:
    models: list[ModelDefinition] = []
    seen: set[str] = set()
    for index, provider_model_name in enumerate(settings.huggingface_coding_models):
        normalized_name = provider_model_name.strip()
        if not normalized_name or normalized_name in seen:
            continue
        seen.add(normalized_name)
        profile = _huggingface_profile(normalized_name, index=index, priorities=priorities)
        model_id = "huggingface-primary" if index == 0 else f"huggingface-{_slugify(normalized_name)}"
        enabled = model_id not in disabled
        models.append(
            ModelDefinition(
                model_id=model_id,
                provider_id="huggingface",
                provider_model_name=normalized_name,
                display_name=profile[0],
                enabled=enabled,
                available=bool(settings.huggingface_api_key),
                capabilities=profile[1],
                allowed_workloads=profile[2],
                context_window=profile[3],
                supports_tools=profile[4],
                supports_streaming=True,
                relative_speed=profile[5],
                relative_quality=profile[6],
                relative_cost=profile[7],
                priority=profile[8],
                tags=profile[9],
                metadata=profile[10],
            )
        )
    return models


def _huggingface_profile(
    provider_model_name: str,
    *,
    index: int,
    priorities: dict[str, int],
) -> tuple[str, frozenset[str], frozenset[Workload], int, bool, int, int, int, int, tuple[str, ...], dict[str, str]]:
    lower = provider_model_name.lower()
    base_priority = priorities.get("huggingface", 0)
    workloads = frozenset({Workload.NORMAL_CHAT, Workload.SPECIALIST, Workload.SOFTWARE_ENGINEERING})
    coding_caps = frozenset({"coding", "reasoning", "long_context"})

    if "devstral" in lower:
        return (
            "Devstral Small 1.1",
            coding_caps,
            workloads,
            128000,
            True,
            6,
            10,
            2,
            base_priority + 30,
            ("free_coding", "agentic"),
            {"family": "devstral", "tier": "primary"},
        )
    if "qwen2.5-coder-7b" in lower:
        return (
            "Qwen2.5 Coder 7B Instruct",
            coding_caps,
            workloads,
            128000,
            True,
            8,
            9,
            1,
            base_priority + 24,
            ("free_coding", "balanced"),
            {"family": "qwen2.5-coder", "tier": "balanced"},
        )
    if "starcoder2-3b" in lower:
        return (
            "StarCoder2 3B",
            coding_caps,
            workloads,
            16384,
            False,
            10,
            7,
            1,
            base_priority + 18,
            ("free_coding", "fast"),
            {"family": "starcoder2", "tier": "speed"},
        )
    if "deepseek-coder-v2-lite" in lower:
        return (
            "DeepSeek Coder V2 Lite Instruct",
            coding_caps,
            workloads,
            128000,
            True,
            7,
            9,
            2,
            base_priority + 22,
            ("free_coding", "long_context"),
            {"family": "deepseek-coder", "tier": "long_context"},
        )

    readable = re.sub(r"[-_]+", " ", provider_model_name.split("/")[-1]).strip()
    return (
        readable.title(),
        coding_caps,
        workloads,
        32768,
        False,
        max(4, 8 - index),
        7,
        2,
        base_priority + max(8, 20 - index * 2),
        ("free_coding", "generic"),
        {"family": "huggingface", "tier": "generic"},
    )


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "model"
