from __future__ import annotations

from datetime import datetime, timezone

from app.models.integration import Integration
from app.services.integrations.schemas import TokenPayload


class TokenManager:
    def apply(self, integration: Integration, payload: TokenPayload) -> Integration:
        integration.access_token = payload.access_token
        if payload.refresh_token:
            integration.refresh_token = payload.refresh_token
        integration.token_expires_at = payload.expires_at
        integration.provider_account_id = payload.provider_account_id or integration.provider_account_id
        integration.provider_email = payload.provider_email or integration.provider_email
        integration.metadata_json = {**(integration.metadata_json or {}), **payload.metadata}
        integration.status = "connected"
        return integration

    def is_expired(self, integration: Integration) -> bool:
        if not integration.token_expires_at:
            return False
        expires_at = integration.token_expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        return expires_at <= datetime.now(timezone.utc)
