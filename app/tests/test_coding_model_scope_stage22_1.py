import asyncio

import pytest

from app.agents.v2.selector import AgentSelector
from app.core.config.settings import settings
from app.intelligence.ai.errors import AIServiceUnavailableError
from app.intelligence.ai.model_router import ModelRegistry, ModelRouter, RoutingPolicy, Workload, request_for_agent, request_for_chat


def scoped_registry(monkeypatch) -> ModelRegistry:
    monkeypatch.setattr(settings, "openai_api_key", "openai-key")
    monkeypatch.setattr(settings, "nvidia_api_key", "nvidia-key")
    monkeypatch.setattr(settings, "huggingface_api_key", "hf-key")
    monkeypatch.setattr(settings, "groq_api_key", None)
    monkeypatch.setattr(settings, "gemini_api_key", None)
    return ModelRegistry()


@pytest.mark.parametrize(
    "message",
    ["Explain quantum computing", "Summarize this document", "Write an email"],
)
def test_normal_requests_never_enter_hf_or_nvidia_pool(monkeypatch, message):
    selection = AgentSelector().select(message)
    assert "bolt" not in selection.agent_ids
    models = ModelRouter(scoped_registry(monkeypatch)).selections(request_for_chat())
    assert models[0].model.provider_id == "openai"
    assert not {item.model.provider_id for item in models}.intersection({"huggingface", "nvidia"})


@pytest.mark.parametrize("message", ["Build a dental clinic website", "Fix this React error"])
def test_software_development_selects_bolt_coding_pool(monkeypatch, message):
    selection = AgentSelector().select(message)
    assert selection.agent_ids == ["bolt"]
    request = request_for_agent("bolt")
    assert request.workload == Workload.SOFTWARE_ENGINEERING
    providers = {item.model.provider_id for item in ModelRouter(scoped_registry(monkeypatch)).selections(request)}
    assert {"huggingface", "nvidia"}.issubset(providers)


def test_non_bolt_specialist_cannot_use_huggingface_or_nvidia(monkeypatch):
    request = request_for_agent("nova")
    assert request.workload == Workload.SPECIALIST
    providers = {item.model.provider_id for item in ModelRouter(scoped_registry(monkeypatch)).selections(request)}
    assert "huggingface" not in providers
    assert "nvidia" not in providers


class OutcomeProvider:
    def __init__(self, outcome, calls: list[str], name: str):
        self.outcome = outcome
        self.calls = calls
        self.name = name

    async def generate(self, **_kwargs):
        self.calls.append(self.name)
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def test_huggingface_rate_limit_falls_back_within_coding_pool(monkeypatch):
    monkeypatch.setattr(settings, "llm_max_fallbacks", 2)
    registry = scoped_registry(monkeypatch)
    hf = registry.get("huggingface-primary").model_copy(update={"priority": 200})
    nvidia = registry.get("nvidia-nemotron-3-ultra-550b-a55b").model_copy(update={"priority": 100})
    calls: list[str] = []
    limited = AIServiceUnavailableError("limited", retryable=True, provider="huggingface", category="rate_limit")
    router = ModelRouter(
        ModelRegistry([hf, nvidia]),
        {
            "huggingface": lambda: OutcomeProvider(limited, calls, "huggingface"),
            "nvidia": lambda: OutcomeProvider("coding result", calls, "nvidia"),
        },
    )
    result = asyncio.run(router.generate(request_for_agent("bolt"), instructions="code", input_text="build"))
    assert result.content == "coding result"
    assert calls == ["huggingface", "nvidia"]


def test_normal_openai_failure_never_crosses_into_coding_pool(monkeypatch):
    monkeypatch.setattr(settings, "llm_max_fallbacks", 3)
    registry = scoped_registry(monkeypatch)
    calls: list[str] = []
    timeout = AIServiceUnavailableError("timeout", retryable=True, provider="openai", category="timeout")
    router = ModelRouter(
        registry,
        {
            "openai": lambda: OutcomeProvider(timeout, calls, "openai"),
            "huggingface": lambda: OutcomeProvider("must not run", calls, "huggingface"),
            "nvidia": lambda: OutcomeProvider("must not run", calls, "nvidia"),
        },
    )
    with pytest.raises(AIServiceUnavailableError):
        asyncio.run(router.generate(request_for_chat(), instructions="chat", input_text="Explain quantum computing"))
    assert calls == ["openai"]


def test_configured_primary_wins_normal_chat_without_entering_coding_pool(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "openai")
    selected = ModelRouter(scoped_registry(monkeypatch)).selections(request_for_chat())
    assert selected[0].model.provider_id == "openai"
    assert not {item.model.provider_id for item in selected}.intersection({"huggingface", "nvidia"})


@pytest.mark.parametrize("policy", [RoutingPolicy.FAST, RoutingPolicy.BALANCED])
def test_interactive_bolt_policy_prefers_faster_huggingface(monkeypatch, policy):
    selected = ModelRouter(scoped_registry(monkeypatch)).selections(request_for_agent("bolt", policy=policy))
    assert selected[0].model.provider_id == "huggingface"


def test_quality_bolt_policy_prefers_nemotron_ultra(monkeypatch):
    selected = ModelRouter(scoped_registry(monkeypatch)).selections(
        request_for_agent("bolt", policy=RoutingPolicy.QUALITY)
    )
    assert selected[0].model.provider_id == "nvidia"
