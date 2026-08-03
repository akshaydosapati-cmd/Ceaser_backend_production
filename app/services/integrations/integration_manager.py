from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.integration import Integration
from app.services.audit_service import AuditService
from app.services.integrations.connection_service import ConnectionService
from app.services.integrations.integration_sync_service import IntegrationSyncService
from app.services.integrations.oauth_manager import OAuthManager
from app.services.integrations.provider_registry import ProviderRegistry
from app.services.integrations.token_manager import TokenManager


LAUNCH_DISABLED_PROVIDERS = {
    "google-calendar",
    "gmail",
    "google-drive",
    "google-tasks",
    "google-classroom",
}


class IntegrationManager:
    def __init__(self, db: Session):
        self.db = db
        self.connections = ConnectionService(db)
        self.registry = ProviderRegistry()
        self.oauth = OAuthManager()
        self.tokens = TokenManager()
        self.sync_service = IntegrationSyncService()

    def providers(self) -> list[dict]:
        return [provider.definition().model_dump() for provider in self.registry.list()]

    def list(self, user_id: str) -> list[dict]:
        records = {record.provider: record for record in self.connections.list(user_id)}
        return [self._read(provider_id, records.get(provider_id)) for provider_id in self.registry.providers]

    def status(self, user_id: str, provider_id: str) -> dict:
        provider = self.registry.get(provider_id)
        return provider.get_status(self.connections.get(user_id=user_id, provider=provider_id))

    def start_connect(self, user_id: str, provider_id: str, workspace_id: str | None = None, return_url: str | None = None) -> dict:
        self.registry.get(provider_id)
        if provider_id in LAUNCH_DISABLED_PROVIDERS:
            raise ValueError("This integration is being prepared for verified access.")
        integration = self.connections.get_or_create(user_id=user_id, provider=provider_id, workspace_id=workspace_id)
        start = self.oauth.start(provider_id)
        integration.metadata_json = {
            **(integration.metadata_json or {}),
            "oauth_state": start.state,
            **({"return_url": return_url} if return_url else {}),
        }
        if start.requires_credentials:
            integration.status = "credentials_required"
        self.db.commit()
        self.db.refresh(integration)
        return {**start.model_dump(), "integration": self._read(provider_id, integration)}

    def complete_connect(self, user_id: str, provider_id: str, code: str, workspace_id: str | None = None) -> Integration:
        if provider_id in LAUNCH_DISABLED_PROVIDERS:
            raise ValueError("This integration is being prepared for verified access.")
        integration = self.connections.get_or_create(user_id=user_id, provider=provider_id, workspace_id=workspace_id)
        payload = self.oauth.exchange_code(provider_id, code)
        self.tokens.apply(integration, payload)
        AuditService(self.db).record(user_id=user_id, action="integration_connected", resource_type="integration", resource_id=integration.id, metadata={"provider": provider_id}, commit=False)
        self.db.commit()
        self.db.refresh(integration)
        return integration

    def complete_connect_by_state(self, provider_id: str, code: str, state: str) -> Integration:
        self.registry.get(provider_id)
        if provider_id in LAUNCH_DISABLED_PROVIDERS:
            raise ValueError("This integration is being prepared for verified access.")
        integration = self.connections.get_by_oauth_state(provider=provider_id, state=state)
        if not integration:
            raise ValueError("OAuth session expired. Start the connection again from CEASER.")
        payload = self.oauth.exchange_code(provider_id, code)
        self.tokens.apply(integration, payload)
        integration.metadata_json = {k: v for k, v in (integration.metadata_json or {}).items() if k != "oauth_state"}
        try:
            self.sync_service.sync(integration)
        except Exception as exc:
            integration.metadata_json = {**(integration.metadata_json or {}), "last_sync_error": str(exc)}
        AuditService(self.db).record(user_id=integration.user_id, action="integration_connected", resource_type="integration", resource_id=integration.id, metadata={"provider": provider_id}, commit=False)
        self.db.commit()
        self.db.refresh(integration)
        return integration

    def disconnect(self, user_id: str, provider_id: str) -> Integration:
        provider = self.registry.get(provider_id)
        integration = self.connections.get_or_create(user_id=user_id, provider=provider_id)
        provider.disconnect(integration)
        AuditService(self.db).record(user_id=user_id, action="integration_disconnected", resource_type="integration", resource_id=integration.id, metadata={"provider": provider_id}, commit=False)
        self.db.commit()
        self.db.refresh(integration)
        return integration

    def refresh(self, user_id: str, provider_id: str) -> Integration:
        provider = self.registry.get(provider_id)
        integration = self.connections.get_or_create(user_id=user_id, provider=provider_id)
        provider.refresh_token(integration)
        AuditService(self.db).record(user_id=user_id, action="integration_token_refreshed", resource_type="integration", resource_id=integration.id, metadata={"provider": provider_id}, commit=False)
        self.db.commit()
        self.db.refresh(integration)
        return integration

    def metadata(self, user_id: str, provider_id: str) -> dict:
        provider = self.registry.get(provider_id)
        integration = self.connections.get(user_id=user_id, provider=provider_id)
        if integration and integration.status == "connected":
            cached = (integration.metadata_json or {}).get("last_metadata")
            if isinstance(cached, dict):
                return cached
        return provider.get_metadata(integration)

    def sync(self, user_id: str, provider_id: str) -> Integration:
        integration = self.connections.get_or_create(user_id=user_id, provider=provider_id)
        try:
            self.sync_service.sync(integration)
            AuditService(self.db).record(user_id=user_id, action="integration_sync_completed", resource_type="integration", resource_id=integration.id, metadata={"provider": provider_id}, commit=False)
        except Exception as exc:
            integration.metadata_json = {**(integration.metadata_json or {}), "last_sync_error": str(exc)}
            AuditService(self.db).record(user_id=user_id, action="integration_sync_failed", resource_type="integration", resource_id=integration.id, metadata={"provider": provider_id, "error": str(exc)}, commit=False)
        self.db.commit()
        self.db.refresh(integration)
        return integration

    def sync_if_stale(self, user_id: str, provider_id: str, *, max_age_seconds: int = 300) -> Integration:
        integration = self.connections.get_or_create(user_id=user_id, provider=provider_id)
        try:
            self.sync_service.sync_if_stale(integration, max_age_seconds=max_age_seconds)
        except Exception as exc:
            integration.metadata_json = {**(integration.metadata_json or {}), "last_sync_error": str(exc)}
        self.db.commit()
        self.db.refresh(integration)
        return integration

    def _read(self, provider_id: str, integration: Integration | None) -> dict:
        provider = self.registry.get(provider_id)
        status = provider.get_status(integration)
        definition = provider.definition().model_dump()
        if provider_id in LAUNCH_DISABLED_PROVIDERS:
            definition = {
                **definition,
                "description": "Prepared for verified Google Workspace access after launch.",
                "scopes": [],
                "permissions": [],
            }
            status = {
                "provider": provider_id,
                "status": "coming_soon",
                "connected": False,
                "account_email": None,
                "last_sync_at": None,
                "permissions": [],
            }
        return {
            **definition,
            **status,
            "provider_account_id": integration.provider_account_id if integration else None,
            "connection_id": integration.id if integration else None,
            "metadata": integration.metadata_json if integration else {},
            "token_expires_at": integration.token_expires_at.isoformat() if integration and integration.token_expires_at else None,
        }
