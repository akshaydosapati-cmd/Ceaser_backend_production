from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
from typing import Any

from sqlalchemy.orm import Session

from app.models.integration import Integration
from app.services.audit_service import AuditService
from app.services.integrations.provider_registry import ProviderRegistry

logger = logging.getLogger(__name__)


@dataclass
class IntegrationToolResult:
    provider: str
    capability: str
    status: str
    data: dict[str, Any] = field(default_factory=dict)
    summary: str = ""
    source: str = "live_api"
    fetched_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    warnings: list[str] = field(default_factory=list)


class IntegrationExecutionEngine:
    def __init__(self, db: Session):
        self.db = db
        self.registry = ProviderRegistry()

    def execute(self, *, user_id: str, provider: str, capability: str, arguments: dict, request_id: str | None = None) -> IntegrationToolResult:
        provider_impl = self.registry.get(provider)
        integration = self.db.query(Integration).filter(Integration.user_id == user_id, Integration.provider == provider).first()
        if not integration or integration.status != "connected":
            return IntegrationToolResult(provider=provider, capability=capability, status="not_connected", summary=f"{provider_impl.name} is not connected.")

        method_name = capability.split(".", 1)[1] if "." in capability else capability
        method = getattr(provider_impl, method_name, None)
        if not callable(method):
            return IntegrationToolResult(provider=provider, capability=capability, status="unsupported", summary=f"{provider_impl.name} does not support this action yet.")

        try:
            data = method(integration, **arguments)
            result = IntegrationToolResult(
                provider=provider,
                capability=capability,
                status="completed",
                data=data if isinstance(data, dict) else {"result": data},
                summary=self._summary(capability, data if isinstance(data, dict) else {}),
            )
            AuditService(self.db).record(
                user_id=user_id,
                action="integration_capability_executed",
                resource_type="integration",
                resource_id=integration.id,
                metadata={"provider": provider, "capability": capability, "request_id": request_id},
                commit=False,
            )
            return result
        except Exception as exc:
            logger.warning("Integration capability failed provider=%s capability=%s error=%s", provider, capability, type(exc).__name__)
            return IntegrationToolResult(provider=provider, capability=capability, status="failed", summary="I could not complete that integration action right now.", warnings=[type(exc).__name__])

    def _summary(self, capability: str, data: dict[str, Any]) -> str:
        if capability == "github.list_repositories":
            return f"Found {len(data.get('repositories') or [])} visible repositories."
        if capability in {"github.resolve_repository", "github.summarize_repositories"}:
            return f"Found {len(data.get('repositories') or [])} matching repositories."
        if capability == "github.list_commits":
            return f"Found {len(data.get('commits') or [])} recent commits."
        if capability == "github.list_issues":
            return f"Found {len(data.get('issues') or [])} open issues."
        if capability == "github.list_pull_requests":
            return f"Found {len(data.get('pull_requests') or [])} open pull requests."
        if capability == "notion.list_tasks":
            return f"Found {len(data.get('tasks') or [])} visible Notion tasks."
        if capability == "notion.list_databases":
            return f"Found {len(data.get('databases') or [])} visible Notion databases."
        if capability == "notion.list_pages":
            return f"Found {len(data.get('pages') or [])} visible Notion pages."
        return "Integration action completed."
