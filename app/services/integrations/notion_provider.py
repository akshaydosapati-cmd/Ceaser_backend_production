import base64
from datetime import datetime, timedelta, timezone

import httpx

from app.core.config.settings import settings
from app.services.integrations.base_provider import BaseIntegrationProvider
from app.services.integrations.schemas import TokenPayload


class NotionProvider(BaseIntegrationProvider):
    id = "notion"
    name = "Notion"
    category = "knowledge"
    description = "Read pages, databases, blocks, titles, and metadata."
    scopes = ["read_content"]
    auth_url = "https://api.notion.com/v1/oauth/authorize"
    token_url = "https://api.notion.com/v1/oauth/token"

    @property
    def client_id(self) -> str | None:
        return settings.notion_client_id

    @property
    def client_secret(self) -> str | None:
        return settings.notion_client_secret

    @property
    def redirect_uri(self) -> str:
        return settings.notion_oauth_redirect_uri

    def authorization_url(self, *, state: str) -> str:
        from urllib.parse import urlencode

        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "owner": "user",
            "state": state,
        }
        return f"{self.auth_url}?{urlencode(params)}"

    def exchange_code(self, code: str) -> TokenPayload:
        credentials = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
        with httpx.Client(timeout=20) as client:
            response = client.post(
                self.token_url,
                headers={"Authorization": f"Basic {credentials}", "Content-Type": "application/json"},
                json={"grant_type": "authorization_code", "code": code, "redirect_uri": self.redirect_uri},
            )
            response.raise_for_status()
        payload = response.json()
        owner = payload.get("owner", {}).get("user", {})
        return TokenPayload(
            access_token=payload["access_token"],
            refresh_token=None,
            expires_at=datetime.now(timezone.utc) + timedelta(days=3650),
            provider_account_id=owner.get("id") or payload.get("workspace_id"),
            provider_email=owner.get("person", {}).get("email"),
            metadata={"workspace_name": payload.get("workspace_name"), "workspace_id": payload.get("workspace_id"), "bot_id": payload.get("bot_id")},
        )
