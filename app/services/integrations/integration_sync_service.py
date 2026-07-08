from __future__ import annotations

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
        metadata = provider.get_metadata(integration)
        if metadata.get("account_email") and not integration.provider_email:
            integration.provider_email = metadata.get("account_email")
        integration.metadata_json = {**(integration.metadata_json or {}), "last_metadata": metadata}
        integration.last_sync_at = utc_now()
        return integration
