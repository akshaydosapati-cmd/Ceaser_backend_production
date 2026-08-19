import asyncio

import pytest

from app.core.config.settings import settings
from app.intelligence.ai.errors import AIServiceUnavailableError
from app.intelligence.ai.model_router import (
    FailureCategory, HealthState, ModelDefinition, ModelRegistry, ModelRequest, ModelRouter, RoutingPolicy,
    request_for_agent, request_for_chat,
)


def model(model_id: str, provider: str, capabilities: set[str], *, speed=5, quality=5, cost=5, tools=False, vision=False, context=1000, enabled=True):
    return ModelDefinition(
        model_id=model_id, provider_id=provider, provider_model_name=model_id, display_name=model_id,
        capabilities=frozenset(capabilities), context_window=context, supports_tools=tools, supports_vision=vision,
        relative_speed=speed, relative_quality=quality, relative_cost=cost, enabled=enabled,
    )


def request(*, required={"general"}, preferred=set(), policy=RoutingPolicy.BALANCED, tools=False, vision=False, context=0):
    return ModelRequest(
        request_id="request-1", required_capabilities=frozenset(required), preferred_capabilities=frozenset(preferred),
        policy=policy, needs_tools=tools, needs_vision=vision, context_size_estimate=context,
    )


def test_registry_validation_duplicate_disabled_and_queries():
    first = model("one", "p1", {"general", "coding"})
    disabled = model("two", "p2", {"general"}, enabled=False)
    registry = ModelRegistry([first, disabled])
    assert registry.enabled() == [first]
    assert registry.by_capability("coding") == [first]
    assert registry.by_provider("p1") == [first]
    with pytest.raises(ValueError, match="Duplicate model ID"):
        registry.register(first)


def test_hard_eligibility_filters_vision_tools_context_and_unavailable():
    models = [
        model("plain", "plain", {"general"}, context=100),
        model("capable", "capable", {"general"}, tools=True, vision=True, context=2000),
    ]
    router = ModelRouter(ModelRegistry(models), {"plain": object, "capable": object})
    assert [item.model.model_id for item in router.selections(request(vision=True))] == ["capable"]
    assert [item.model.model_id for item in router.selections(request(tools=True))] == ["capable"]
    assert [item.model.model_id for item in router.selections(request(context=1500))] == ["capable"]
    router._state("capable")["state"] = HealthState.UNAVAILABLE
    assert router.selections(request(vision=True)) == []


@pytest.mark.parametrize(("policy", "winner"), [
    (RoutingPolicy.FAST, "fast"), (RoutingPolicy.QUALITY, "quality"), (RoutingPolicy.ECONOMY, "cheap"),
])
def test_policy_scoring(policy, winner):
    registry = ModelRegistry([
        model("fast", "fast", {"general"}, speed=10, quality=5, cost=5),
        model("quality", "quality", {"general"}, speed=5, quality=10, cost=5),
        model("cheap", "cheap", {"general"}, speed=5, quality=5, cost=1),
    ])
    assert ModelRouter(registry).selections(request(policy=policy))[0].model.model_id == winner


def test_required_capability_outweighs_preference():
    registry = ModelRegistry([
        model("coding", "coding", {"general", "coding"}, speed=3),
        model("fast", "fast", {"general", "fast"}, speed=10),
    ])
    selected = ModelRouter(registry).selections(request(required={"coding"}, preferred={"fast"}, policy=RoutingPolicy.FAST))
    assert [item.model.model_id for item in selected] == ["coding"]


@pytest.mark.parametrize(("agent_id", "required", "preferred"), [
    ("bolt", "coding", "tool_use"), ("alex", "reasoning", "long_context"),
    ("nova", "creative", "fast"), ("zeus", "reasoning", "long_context"),
    ("atlas", "general", "structured_output"), ("friday", "general", "tool_use"),
])
def test_agent_model_requests(agent_id, required, preferred):
    result = request_for_agent(agent_id)
    assert required in result.required_capabilities
    assert preferred in result.preferred_capabilities
    assert result.agent_id == agent_id


class FakeProvider:
    def __init__(self, outcome):
        self.outcome = outcome

    async def generate(self, **_kwargs):
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def test_timeout_falls_back_and_emits_events(monkeypatch):
    monkeypatch.setattr(settings, "llm_max_fallbacks", 2)
    timeout = AIServiceUnavailableError("timed out", provider="p1", category="timeout", retryable=True)
    router = ModelRouter(
        ModelRegistry([model("m1", "p1", {"general"}, quality=10), model("m2", "p2", {"general"}, quality=8)]),
        {"p1": lambda: FakeProvider(timeout), "p2": lambda: FakeProvider("ok")},
    )
    response = asyncio.run(router.generate(request(), instructions="safe", input_text="hello"))
    assert response.content == "ok" and response.fallback_used and response.attempt_count == 2
    assert router.snapshot()["m1"]["state"] == "cooldown"
    assert {event.event for event in router.events}.issuperset({"model.selected", "model.attempt_failed", "model.fallback", "model.completed"})


def test_rate_limit_cooldown_and_incompatible_fallback_excluded(monkeypatch):
    monkeypatch.setattr(settings, "llm_max_fallbacks", 2)
    limited = AIServiceUnavailableError("limited", provider="p1", category="rate_limit", retryable=True)
    router = ModelRouter(
        ModelRegistry([model("reasoner", "p1", {"reasoning"}), model("general", "p2", {"general"})]),
        {"p1": lambda: FakeProvider(limited), "p2": lambda: FakeProvider("must not run")},
    )
    with pytest.raises(AIServiceUnavailableError):
        asyncio.run(router.generate(request(required={"reasoning"}), instructions="safe", input_text="hello"))
    assert router.classify_failure(limited) == FailureCategory.RATE_LIMIT


def test_authentication_failure_stops_bounded_fallback(monkeypatch):
    monkeypatch.setattr(settings, "llm_max_fallbacks", 3)
    auth = AIServiceUnavailableError("invalid credential", provider="p1", category="authentication", retryable=False)
    called = []
    router = ModelRouter(
        ModelRegistry([model("m1", "p1", {"general"}, quality=10), model("m2", "p2", {"general"})]),
        {"p1": lambda: FakeProvider(auth), "p2": lambda: FakeProvider(called.append("called"))},
    )
    with pytest.raises(AIServiceUnavailableError):
        asyncio.run(router.generate(request(), instructions="safe", input_text="hello"))
    assert not any(event.event == "model.fallback" for event in router.events)


def test_normal_chat_routes_general_model():
    router = ModelRouter(ModelRegistry([model("general", "p", {"general", "fast"})]))
    selected = router.selections(request_for_chat())
    assert selected[0].model.model_id == "general"


def test_software_workload_prefers_purpose_configured_model():
    from app.intelligence.ai.model_router.models import Workload

    generic = model("generic", "openai", {"coding", "reasoning"}, quality=10)
    dedicated = model("dedicated", "nvidia", {"coding", "reasoning", "tool_use"}, quality=8)
    dedicated.allowed_workloads = frozenset({Workload.SOFTWARE_ENGINEERING})
    software_request = request_for_agent("bolt")
    selected = ModelRouter(ModelRegistry([generic, dedicated])).selections(software_request)
    assert selected[0].model.model_id == "dedicated"


def test_missing_credentials_disable_configured_models_without_crash(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", None)
    monkeypatch.setattr(settings, "groq_api_key", None)
    monkeypatch.setattr(settings, "gemini_api_key", None)
    monkeypatch.setattr(settings, "huggingface_api_key", None)
    monkeypatch.setattr(settings, "nvidia_api_key", None)
    registry = ModelRegistry()
    assert registry.enabled() == []
    assert len(registry.safe_metadata()) == 8


def test_observability_never_contains_secrets():
    router = ModelRouter(ModelRegistry([model("general", "p", {"general"})]))
    router.selections(ModelRequest(request_id="r", metadata={"api_key": "secret"}))
    payload = " ".join(str(event.model_dump()) for event in router.events)
    assert "secret" not in payload and "api_key" not in payload
