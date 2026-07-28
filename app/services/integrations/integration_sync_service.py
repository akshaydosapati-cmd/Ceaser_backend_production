from __future__ import annotations

from datetime import timedelta

from app.models.integration import Integration
from app.models.mixins import utc_now
from app.services.integrations.provider_registry import ProviderRegistry
from app.services.integrations.token_manager import TokenManager


class IntegrationSyncService:
    def __init__(self):
        self.registry = ProviderRegistry()
        self.tokens = TokenManager()

    def sync(self, integration: Integration) -> Integration:
        provider = self.registry.get(integration.provider)
        if integration.status != "connected":
            return integration
        if self.tokens.is_expired(integration):
            provider.refresh_token(integration)
        try:
            metadata = provider.get_metadata(integration)
            if metadata.get("account_email") and not integration.provider_email:
                integration.provider_email = metadata.get("account_email")
            integration.metadata_json = {
                **(integration.metadata_json or {}),
                "last_metadata": metadata,
                "last_sync_error": None,
            }
        except Exception as exc:
            integration.metadata_json = {
                **(integration.metadata_json or {}),
                "last_sync_error": str(exc),
            }
        integration.last_sync_at = utc_now()
        return integration

    def sync_if_stale(self, integration: Integration, *, max_age_seconds: int = 300) -> Integration:
        if integration.status != "connected":
            return integration
        if integration.last_sync_at:
            age = utc_now() - integration.last_sync_at
            if age <= timedelta(seconds=max_age_seconds):
                return integration
        return self.sync(integration)
