from __future__ import annotations

from abc import ABC
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx

from app.core.config.settings import settings
from app.models.integration import Integration
from app.services.integrations.schemas import OAuthStart, ProviderDefinition, TokenPayload


class BaseIntegrationProvider(ABC):
    id: str
    name: str
    category: str
    description: str
    scopes: list[str]
    auth_url: str
    token_url: str

    @property
    def permissions(self) -> list[str]:
        return self.scopes

    def definition(self) -> ProviderDefinition:
        return ProviderDefinition(
            id=self.id,
            name=self.name,
            category=self.category,
            description=self.description,
            scopes=self.scopes,
            permissions=self.permissions,
        )

    def connect(self, *, state: str) -> OAuthStart:
        if not self.client_id:
            return OAuthStart(auth_url="", state=state, provider=self.id, requires_credentials=True)
        return OAuthStart(auth_url=self.authorization_url(state=state), state=state, provider=self.id)

    def disconnect(self, integration: Integration) -> None:
        integration.status = "not_connected"
        integration.access_token = None
        integration.refresh_token = None
        integration.token_expires_at = None
        integration.metadata_json = {}
        integration.provider_account_id = None
        integration.provider_email = None

    def refresh_token(self, integration: Integration) -> Integration:
        if not integration.refresh_token:
            integration.status = "needs_reconnect"
            return integration
        payload = self.exchange_refresh_token(integration.refresh_token)
        integration.access_token = payload.access_token
        if payload.refresh_token:
            integration.refresh_token = payload.refresh_token
        integration.token_expires_at = payload.expires_at
        integration.status = "connected"
        return integration

    def get_status(self, integration: Integration | None) -> dict:
        if not integration:
            return {"provider": self.id, "status": "not_connected", "connected": False}
        return {
            "provider": self.id,
            "status": integration.status,
            "connected": integration.status == "connected",
            "account_email": integration.provider_email,
            "last_sync_at": integration.last_sync_at.isoformat() if integration.last_sync_at else None,
            "permissions": self.permissions,
        }

    def get_metadata(self, integration: Integration | None) -> dict:
        if not integration or integration.status != "connected":
            return {"provider": self.id, "status": "not_connected", "items": []}
        return {
            "provider": self.id,
            "status": integration.status,
            "account_email": integration.provider_email,
            "permissions": self.permissions,
            "metadata": integration.metadata_json or {},
        }

    def google_get(self, integration: Integration, url: str, params: dict | None = None) -> dict:
        with httpx.Client(timeout=20) as client:
            response = client.get(
                url,
                params=params or {},
                headers={"Authorization": f"Bearer {integration.access_token}"},
            )
            response.raise_for_status()
            return response.json()

    def google_request(self, integration: Integration, method: str, url: str, *, payload: dict | None = None) -> dict:
        with httpx.Client(timeout=20) as client:
            response = client.request(method, url, json=payload or {}, headers={"Authorization": f"Bearer {integration.access_token}", "Content-Type": "application/json"})
            response.raise_for_status()
            return response.json()

    def authorization_url(self, *, state: str) -> str:
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": " ".join(self.scopes),
            "state": state,
            "access_type": "offline",
            "prompt": "consent",
        }
        return f"{self.auth_url}?{urlencode(params)}"

    def exchange_code(self, code: str) -> TokenPayload:
        with httpx.Client(timeout=20) as client:
            response = client.post(
                self.token_url,
                data={
                    "code": code,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "redirect_uri": self.redirect_uri,
                    "grant_type": "authorization_code",
                },
            )
            response.raise_for_status()
        return self._token_payload(response.json())

    def exchange_refresh_token(self, refresh_token: str) -> TokenPayload:
        with httpx.Client(timeout=20) as client:
            response = client.post(
                self.token_url,
                data={
                    "refresh_token": refresh_token,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "grant_type": "refresh_token",
                },
            )
            response.raise_for_status()
        return self._token_payload(response.json(), fallback_refresh_token=refresh_token)

    def _token_payload(self, payload: dict, fallback_refresh_token: str | None = None) -> TokenPayload:
        expires_in = int(payload.get("expires_in") or 3600)
        return TokenPayload(
            access_token=payload["access_token"],
            refresh_token=payload.get("refresh_token") or fallback_refresh_token,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=expires_in),
            metadata={"token_type": payload.get("token_type"), "scope": payload.get("scope")},
        )

    @property
    def client_id(self) -> str | None:
        return settings.google_client_id

    @property
    def client_secret(self) -> str | None:
        return settings.google_client_secret

    @property
    def redirect_uri(self) -> str:
        return settings.google_oauth_redirect_uri
