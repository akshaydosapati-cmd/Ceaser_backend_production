from __future__ import annotations

from app.core.config.settings import Settings
from app.intelligence.ai.model_router.models import ModelRequest, Workload
from app.intelligence.ai.model_router.registry import ModelRegistry
from app.intelligence.ai.model_router.router import ModelRouter


def _production_settings(**overrides) -> Settings:
    values = {
        "CEASER_ENV": "production",
        "DATABASE_URL": "postgresql+psycopg://user:pass@db.example/ceaser",
        "SUPABASE_URL": "https://project.supabase.co",
        "SUPABASE_ANON_KEY": "public-anon",
        "SUPABASE_SERVICE_ROLE_KEY": "server-only",
        "JWT_SECRET": "jwt-secret",
        "ENCRYPTION_MASTER_KEY": "encryption-secret",
        "FRONTEND_APP_URL": "https://console.example.com",
        "CORS_ORIGINS": "https://console.example.com",
        "OPENAI_API_KEY": "provider-secret",
        "DEV_AUTH_BYPASS": False,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_stage29_production_contract(monkeypatch):
    incomplete = Settings(
        _env_file=None,
        CEASER_ENV="production",
        DATABASE_URL="postgresql+psycopg://postgres:postgres@localhost:5432/ceaser",
        CORS_ORIGINS="http://localhost:3000",
        FRONTEND_APP_URL="http://localhost:3000",
        DEV_AUTH_BYPASS=True,
        OPENAI_API_KEY="",
        GROQ_API_KEY="",
        GEMINI_API_KEY="",
    )
    errors = incomplete.production_configuration_errors()
    assert "DATABASE_URL(non-local)" in errors
    assert "CORS_ORIGINS(non-local)" in errors
    assert "NORMAL_CHAT_PROVIDER_KEY" in errors

    configured = _production_settings()
    assert configured.production_configuration_errors() == []
    assert configured.local_coding_enabled is True
    assert configured.cloud_coding_enabled is False

    from app.intelligence.ai.model_router import registry as registry_module
    from app.intelligence.ai.model_router import router as router_module

    monkeypatch.setattr(registry_module, "settings", configured)
    monkeypatch.setattr(router_module, "settings", configured)
    registry = ModelRegistry()
    router = ModelRouter(registry=registry, provider_factories={})
    request = ModelRequest(
        request_id="stage29-normal-chat",
        workload=Workload.NORMAL_CHAT,
        required_capabilities=frozenset({"general"}),
    )
    providers = [selection.model.provider_id for selection in router.selections(request)]
    assert "openai" in providers
    assert "nvidia" not in providers
    assert "huggingface" not in providers
