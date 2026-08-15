import asyncio

import httpx
import pytest

from app.core.config.settings import settings
from app.intelligence.ai.errors import AIServiceUnavailableError
from app.intelligence.ai.llm.nvidia_provider import NvidiaProvider
from app.intelligence.ai.llm.http_errors import ai_error_from_status
from app.intelligence.ai.model_router import ModelRegistry, ModelRouter, request_for_agent, request_for_chat


def configured_registry(monkeypatch, *, nvidia_key: str | None = "configured") -> ModelRegistry:
    monkeypatch.setattr(settings, "nvidia_api_key", nvidia_key)
    monkeypatch.setattr(settings, "openai_api_key", None)
    monkeypatch.setattr(settings, "groq_api_key", None)
    monkeypatch.setattr(settings, "gemini_api_key", None)
    monkeypatch.setattr(settings, "huggingface_api_key", None)
    return ModelRegistry()


def test_nvidia_model_registration_and_missing_key(monkeypatch):
    registry = configured_registry(monkeypatch, nvidia_key=None)
    model = registry.get("nvidia-nemotron-3-ultra-550b-a55b")
    assert model is not None
    assert model.provider_model_name == "nvidia/nemotron-3-ultra-550b-a55b"
    assert {"general", "reasoning", "coding", "tool_use", "long_context"}.issubset(model.capabilities)
    assert model.supports_tools and model.supports_streaming
    assert model.context_window == 1000000
    assert model not in registry.enabled()


def test_bolt_can_select_nemotron_through_normal_scoring(monkeypatch):
    registry = configured_registry(monkeypatch)
    selected = ModelRouter(registry).selections(request_for_agent("bolt"))
    assert selected[0].model.provider_id == "nvidia"
    assert "coding" in selected[0].model.capabilities
    assert {"reasoning", "tool_use"}.issubset(selected[0].model.capabilities)


def test_normal_chat_remains_compatible(monkeypatch):
    monkeypatch.setattr(settings, "nvidia_api_key", "configured")
    monkeypatch.setattr(settings, "openai_api_key", "configured")
    monkeypatch.setattr(settings, "groq_api_key", None)
    monkeypatch.setattr(settings, "gemini_api_key", None)
    monkeypatch.setattr(settings, "huggingface_api_key", None)
    registry = ModelRegistry()
    selected = ModelRouter(registry).selections(request_for_chat())
    assert selected and selected[0].model.provider_id == "openai"
    assert all(item.model.provider_id != "nvidia" for item in selected)


class OutcomeProvider:
    def __init__(self, outcome):
        self.outcome = outcome

    async def generate(self, **_kwargs):
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def test_nvidia_timeout_uses_existing_router_fallback(monkeypatch):
    monkeypatch.setattr(settings, "llm_max_fallbacks", 1)
    timeout = NvidiaProvider._request_error(httpx.ReadTimeout("timed out"))
    registry = configured_registry(monkeypatch)
    fallback = registry.get("openai-primary").model_copy(update={"available": True, "priority": 0})
    nvidia = registry.get("nvidia-nemotron-3-ultra-550b-a55b").model_copy(update={"priority": 100})
    router = ModelRouter(
        ModelRegistry([nvidia, fallback]),
        {"nvidia": lambda: OutcomeProvider(timeout), "openai": lambda: OutcomeProvider("fallback ok")},
    )
    result = asyncio.run(router.generate(request_for_agent("bolt"), instructions="safe", input_text="build app"))
    assert result.content == "fallback ok"
    assert result.fallback_used
    assert router.snapshot()["nvidia"]["last_error"] == "timeout"


@pytest.mark.parametrize("status", [401, 403])
def test_nvidia_auth_error_is_safe_and_non_retryable(status):
    error = NvidiaProvider()._status_error(status, "secret-token-must-not-appear", settings.nvidia_model)
    assert error.category == "authentication"
    assert error.retryable is False
    assert "secret-token-must-not-appear" not in str(error.detail)
    assert "secret-token-must-not-appear" not in str(error)


def test_nvidia_rate_limit_is_retryable():
    error = NvidiaProvider()._status_error(429, "quota", settings.nvidia_model)
    assert error.category == "rate_limit"
    assert error.retryable is True


def test_nvidia_payload_enables_nonempty_coding_agent_content():
    payload = NvidiaProvider._payload(settings.nvidia_model, "build", "create app", 100, False)
    assert payload["chat_template_kwargs"]["force_nonempty_content"] is True
    assert payload["chat_template_kwargs"]["enable_thinking"] is settings.nvidia_enable_thinking


def test_shared_http_auth_classification_redacts_provider_body():
    error = ai_error_from_status(
        status_code=401, body="credential-fragment-must-not-appear", provider="openai"
    )
    assert error.category == "authentication"
    assert error.retryable is False
    assert "credential-fragment-must-not-appear" not in str(error.detail)
