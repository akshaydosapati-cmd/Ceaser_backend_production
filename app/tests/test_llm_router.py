from app.core.config.settings import settings
from app.intelligence.ai.llm.router import AdaptiveLLMRouter


def test_openai_is_primary_and_other_configured_providers_are_fallbacks(monkeypatch) -> None:
    monkeypatch.setattr(settings, "llm_provider_order_raw", "openai,groq,gemini,huggingface")
    monkeypatch.setattr(settings, "openai_api_key", "test-openai-key")
    monkeypatch.setattr(settings, "groq_api_key", "test-groq-key")
    monkeypatch.setattr(settings, "gemini_api_key", "test-gemini-key")
    monkeypatch.setattr(settings, "huggingface_api_key", "test-huggingface-key")

    router = AdaptiveLLMRouter()

    assert [name for name, _provider in router.candidates(max_count=4)] == [
        "openai",
        "groq",
        "gemini",
        "huggingface",
    ]
