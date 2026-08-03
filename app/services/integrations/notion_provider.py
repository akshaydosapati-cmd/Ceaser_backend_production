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

    def list_pages(self, integration, query: str | None = None, **_: object) -> dict:
        metadata = self._cached_or_live_metadata(integration)
        pages = [item for item in metadata.get("items") or [] if item.get("object") == "page"]
        if query:
            pages = self._filter_items(pages, query)
        return {"workspace": metadata.get("workspace_name"), "pages": pages, "query": query or ""}

    def search_pages(self, integration, query: str | None = None, **_: object) -> dict:
        return self.list_pages(integration, query=query)

    def list_databases(self, integration, query: str | None = None, **_: object) -> dict:
        metadata = self._cached_or_live_metadata(integration)
        databases = [item for item in metadata.get("items") or [] if item.get("object") == "database"]
        if query:
            databases = self._filter_items(databases, query)
        return {"workspace": metadata.get("workspace_name"), "databases": databases, "query": query or ""}

    def summarize_workspace(self, integration, **_: object) -> dict:
        metadata = self._cached_or_live_metadata(integration)
        items = metadata.get("items") or []
        return {
            "workspace": metadata.get("workspace_name"),
            "pages": [item for item in items if item.get("object") == "page"],
            "databases": [item for item in items if item.get("object") == "database"],
            "users": metadata.get("users") or [],
        }

    def list_tasks(self, integration, query: str | None = None, **_: object) -> dict:
        metadata = self._cached_or_live_metadata(integration)
        tasks = []
        for database in metadata.get("items") or []:
            if database.get("object") != "database":
                continue
            if "task" not in str(database.get("title") or "").lower() and "todo" not in str(database.get("title") or "").lower():
                continue
            for row in database.get("rows") or []:
                if isinstance(row, dict):
                    tasks.append(row)
        if not tasks:
            metadata = self.get_metadata(integration)
            for database in metadata.get("items") or []:
                if database.get("object") != "database":
                    continue
                if "task" not in str(database.get("title") or "").lower() and "todo" not in str(database.get("title") or "").lower():
                    continue
                for row in database.get("rows") or []:
                    if isinstance(row, dict):
                        tasks.append(row)
        if query:
            tasks = self._filter_items(tasks, query)
        return {"workspace": metadata.get("workspace_name"), "tasks": tasks, "users": metadata.get("users") or [], "query": query or ""}

    def _cached_or_live_metadata(self, integration) -> dict:
        cached = (integration.metadata_json or {}).get("last_metadata")
        if isinstance(cached, dict):
            return cached
        return self.get_metadata(integration)

    def _filter_items(self, items: list[dict], query: str) -> list[dict]:
        needle = query.lower()
        return [
            item
            for item in items
            if needle in " ".join([str(item.get("title") or ""), str(item.get("excerpt") or ""), str(item.get("properties") or "")]).lower()
        ]

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
            summary = {
                "properties": self._database_properties(item),
                "rows": self._database_rows(client, headers, item.get("id"), title),
            }
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

    def _database_rows(self, client: httpx.Client, headers: dict[str, str], database_id: str | None, database_title: str) -> list[dict]:
        if not database_id:
            return []
        try:
            response = client.post(
                f"{self.api_base_url}/databases/{database_id}/query",
                headers=headers,
                json={"page_size": 12},
            )
            if response.status_code >= 400:
                return []
        except Exception:
            return []
        rows: list[dict] = []
        for page in response.json().get("results", []):
            properties = self._page_properties(page)
            title = self._first_property(properties, ("title", "name", "task", "project")) or self._title_from_item(page)
            rows.append(
                {
                    "id": page.get("id"),
                    "title": title or "Untitled",
                    "database": database_title,
                    "url": page.get("url"),
                    "last_edited_time": page.get("last_edited_time"),
                    "properties": properties,
                }
            )
        return rows

    def _page_properties(self, page: dict) -> dict[str, object]:
        properties = page.get("properties") or {}
        values: dict[str, object] = {}
        for name, payload in properties.items():
            if not isinstance(name, str) or not isinstance(payload, dict):
                continue
            value = self._property_value(payload)
            if value not in (None, "", [], {}):
                values[name] = value
        return values

    def _property_value(self, payload: dict) -> object:
        property_type = payload.get("type")
        value = payload.get(property_type) if property_type else None
        if property_type in {"title", "rich_text"} and isinstance(value, list):
            return " ".join(part.get("plain_text", "") for part in value if isinstance(part, dict)).strip()
        if property_type in {"select", "status"} and isinstance(value, dict):
            return value.get("name")
        if property_type == "multi_select" and isinstance(value, list):
            return [item.get("name") for item in value if isinstance(item, dict) and item.get("name")]
        if property_type == "people" and isinstance(value, list):
            people = []
            for item in value:
                if not isinstance(item, dict):
                    continue
                person = item.get("person") if isinstance(item.get("person"), dict) else {}
                people.append({"name": item.get("name") or "Unnamed user", "email": person.get("email")})
            return people
        if property_type == "date" and isinstance(value, dict):
            return value.get("start") or value.get("end")
        if property_type in {"checkbox", "number", "email", "phone_number", "url"}:
            return value
        if property_type == "relation" and isinstance(value, list):
            return [item.get("id") for item in value if isinstance(item, dict) and item.get("id")]
        return None

    def _first_property(self, properties: dict[str, object], names: tuple[str, ...]) -> str | None:
        lower_names = {name.lower() for name in names}
        for name, value in properties.items():
            if name.lower() in lower_names and isinstance(value, str) and value.strip():
                return value.strip()
        for name, value in properties.items():
            if any(token in name.lower() for token in lower_names) and isinstance(value, str) and value.strip():
                return value.strip()
        return None

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
