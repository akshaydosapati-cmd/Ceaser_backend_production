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
    api_base_url = "https://api.notion.com/v1"
    notion_version = "2022-06-28"

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
        return self._exchange_token({"grant_type": "authorization_code", "code": code, "redirect_uri": self.redirect_uri})

    def exchange_refresh_token(self, refresh_token: str) -> TokenPayload:
        return self._exchange_token({"grant_type": "refresh_token", "refresh_token": refresh_token})

    def get_metadata(self, integration) -> dict:
        if not integration or integration.status != "connected":
            return {"provider": self.id, "status": "not_connected", "items": []}

        headers = self._api_headers(integration.access_token)
        with httpx.Client(timeout=20) as client:
            user_response = client.get(f"{self.api_base_url}/users/me", headers=headers)
            user_response.raise_for_status()
            search_response = client.post(
                f"{self.api_base_url}/search",
                headers=headers,
                json={"page_size": 10},
            )
            search_response.raise_for_status()
            users_response = client.get(f"{self.api_base_url}/users", headers=headers, params={"page_size": 25})
            users_response.raise_for_status()
            user_payload = user_response.json()
            search_payload = search_response.json()
            users_payload = users_response.json()
            items = [self._search_item(client, headers, item) for item in search_payload.get("results", [])]
            users = [self._user_item(item) for item in users_payload.get("results", [])]

        return {
            "provider": self.id,
            "status": integration.status,
            "account_email": integration.provider_email,
            "workspace_name": (integration.metadata_json or {}).get("workspace_name"),
            "workspace_id": (integration.metadata_json or {}).get("workspace_id"),
            "bot_id": (integration.metadata_json or {}).get("bot_id"),
            "user": {
                "id": user_payload.get("id"),
                "name": user_payload.get("name"),
                "type": user_payload.get("type"),
            },
            "items": items,
            "item_count": len(items),
            "users": users,
            "user_count": len(users),
            "permissions": self.permissions,
        }

    def _exchange_token(self, body: dict) -> TokenPayload:
        credentials = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
        with httpx.Client(timeout=20) as client:
            response = client.post(
                self.token_url,
                headers={"Authorization": f"Basic {credentials}", "Accept": "application/json", "Content-Type": "application/json"},
                json=body,
            )
            response.raise_for_status()
        payload = response.json()
        owner = payload.get("owner", {}).get("user", {})
        expires_in = payload.get("expires_in")
        return TokenPayload(
            access_token=payload["access_token"],
            refresh_token=payload.get("refresh_token"),
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=int(expires_in)) if expires_in else None,
            provider_account_id=owner.get("id") or payload.get("workspace_id"),
            provider_email=owner.get("person", {}).get("email"),
            metadata={
                "token_type": payload.get("token_type"),
                "workspace_name": payload.get("workspace_name"),
                "workspace_id": payload.get("workspace_id"),
                "workspace_icon": payload.get("workspace_icon"),
                "bot_id": payload.get("bot_id"),
                "owner_type": payload.get("owner", {}).get("type"),
            },
        )

    def _api_headers(self, access_token: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {access_token}",
            "Notion-Version": self.notion_version,
            "Content-Type": "application/json",
        }

    def _search_item(self, client: httpx.Client, headers: dict[str, str], item: dict) -> dict:
        title = self._title_from_item(item)
        object_type = item.get("object")
        summary: dict = {}
        if object_type == "page":
            summary = {"excerpt": self._page_excerpt(client, headers, item.get("id"))}
        elif object_type == "database":
            summary = {"properties": self._database_properties(item)}
        return {
            "id": item.get("id"),
            "object": object_type,
            "title": title,
            "url": item.get("url"),
            "last_edited_time": item.get("last_edited_time"),
            **summary,
        }

    def _page_excerpt(self, client: httpx.Client, headers: dict[str, str], page_id: str | None) -> str:
        if not page_id:
            return ""
        try:
            response = client.get(f"{self.api_base_url}/blocks/{page_id}/children", headers=headers, params={"page_size": 20})
            response.raise_for_status()
        except Exception:
            return ""
        texts: list[str] = []
        for block in response.json().get("results", []):
            text = self._block_text(block)
            if text:
                texts.append(text)
            if len(" ".join(texts)) > 1400:
                break
        return " ".join(texts)[:1600].strip()

    def _block_text(self, block: dict) -> str:
        block_type = block.get("type")
        value = block.get(block_type) if block_type else None
        if not isinstance(value, dict):
            return ""
        rich_text = value.get("rich_text") or value.get("title") or []
        text = " ".join(part.get("plain_text", "") for part in rich_text if isinstance(part, dict)).strip()
        if block_type == "to_do" and text:
            return f"{'[done]' if value.get('checked') else '[todo]'} {text}"
        return text

    def _database_properties(self, item: dict) -> list[str]:
        properties = item.get("properties") or {}
        return [name for name in properties.keys() if isinstance(name, str)][:12]

    def _user_item(self, item: dict) -> dict:
        person = item.get("person") if isinstance(item.get("person"), dict) else {}
        bot = item.get("bot") if isinstance(item.get("bot"), dict) else {}
        return {
            "id": item.get("id"),
            "name": item.get("name") or "Unnamed user",
            "type": item.get("type"),
            "email": person.get("email"),
            "workspace_name": bot.get("workspace_name"),
        }

    def _title_from_item(self, item: dict) -> str:
        if item.get("object") == "page":
            properties = item.get("properties") or {}
            for property_value in properties.values():
                if property_value.get("type") == "title":
                    title = property_value.get("title") or []
                    text = "".join(part.get("plain_text", "") for part in title).strip()
                    if text:
                        return text
        if item.get("object") == "database":
            title = item.get("title") or []
            text = "".join(part.get("plain_text", "") for part in title).strip()
            if text:
                return text
        return "Untitled"
