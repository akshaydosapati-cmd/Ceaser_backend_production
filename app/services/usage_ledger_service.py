from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.commercial import UsageLedger


FEATURES = {
    "chat", "voice", "plugin", "web_search", "document", "presentation",
    "spreadsheet", "image", "workforce", "automation", "native",
}
_SENSITIVE_KEYS = {"authorization", "api_key", "access_token", "refresh_token", "password", "secret", "token"}


def _non_negative(value: int | float | None) -> int | float:
    return max(0, value or 0)


def _safe_metadata(value: dict[str, Any] | None) -> dict[str, Any]:
    if not value:
        return {}
    safe: dict[str, Any] = {}
    for key, item in value.items():
        if key.lower() in _SENSITIVE_KEYS or any(part in key.lower() for part in ("password", "secret", "token", "credential")):
            continue
        if isinstance(item, (str, int, float, bool)) or item is None:
            safe[key] = item
    return safe


class UsageLedgerService:
    """Append/update usage telemetry only. C1 intentionally enforces no policy."""

    def __init__(self, db: Session):
        self.db = db

    def start(
        self,
        *,
        user_id: str,
        request_id: str,
        feature: str,
        operation: str,
        provider: str | None = None,
        model: str | None = None,
        estimated_cost: float = 0,
        idempotency_key: str | None = None,
        capability_key: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> UsageLedger:
        normalized_feature = feature if feature in FEATURES else "automation"
        key = idempotency_key or f"{request_id}:{normalized_feature}:{operation}"
        existing = self.db.query(UsageLedger).filter(UsageLedger.idempotency_key == key).first()
        if existing:
            return existing
        from app.services.capabilities.registry import capability_registry
        manifest = capability_registry.resolve_manifest(capability_key or operation)
        event = UsageLedger(
            user_id=user_id,
            action_type=normalized_feature,
            operation=operation[:120],
            provider=provider[:80] if provider else None,
            model=model[:160] if model else None,
            status="started",
            estimated_cost=float(_non_negative(estimated_cost)),
            request_id=request_id[:120],
            idempotency_key=key[:180],
            capability_key=manifest.key,
            capability_category=manifest.category,
            execution_type=manifest.execution_type,
            extra_metadata=_safe_metadata(metadata),
        )
        self.db.add(event)
        self.db.flush()
        return event

    def complete(
        self,
        event: UsageLedger,
        *,
        status: str = "completed",
        provider: str | None = None,
        model: str | None = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        embedding_tokens: int = 0,
        voice_input_seconds: int = 0,
        voice_output_seconds: int = 0,
        web_searches: int = 0,
        image_generations: int = 0,
        tool_calls: int = 0,
        actual_cost: float = 0,
        metadata: dict[str, Any] | None = None,
    ) -> UsageLedger:
        event.status = status[:30]
        event.provider = (provider or event.provider)
        event.model = (model or event.model)
        event.input_tokens = int(_non_negative(input_tokens))
        event.output_tokens = int(_non_negative(output_tokens))
        event.embedding_tokens = int(_non_negative(embedding_tokens))
        event.voice_input_seconds = int(_non_negative(voice_input_seconds))
        event.voice_output_seconds = int(_non_negative(voice_output_seconds))
        event.voice_seconds = event.voice_input_seconds + event.voice_output_seconds
        event.web_searches = int(_non_negative(web_searches))
        event.image_generations = int(_non_negative(image_generations))
        event.tool_calls = int(_non_negative(tool_calls))
        event.actual_cost = float(_non_negative(actual_cost))
        event.extra_metadata = {**(event.extra_metadata or {}), **_safe_metadata(metadata)}
        from app.services.cost_registry import CostRegistry
        CostRegistry(self.db).price_event(event)
        self.db.flush()
        return event

    def for_request(self, user_id: str, request_id: str) -> list[UsageLedger]:
        return self.db.query(UsageLedger).filter_by(user_id=user_id, request_id=request_id).order_by(UsageLedger.created_at).all()


def feature_for_workload(workload: str) -> str:
    if workload == "ai_conversation":
        return "chat"
    if workload == "research":
        return "web_search"
    if workload in {"agent_workflow", "bolt_development"}:
        return "workforce"
    if workload == "local_command":
        return "native"
    return "automation"
