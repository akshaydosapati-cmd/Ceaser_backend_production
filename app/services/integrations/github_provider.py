from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
from urllib.parse import urlencode

import httpx

from app.core.config.settings import settings
from app.models.integration import Integration
from app.services.integrations.base_provider import BaseIntegrationProvider
from app.services.integrations.schemas import TokenPayload

logger = logging.getLogger(__name__)


class GitHubProvider(BaseIntegrationProvider):
    id = "github"
    name = "GitHub"
    category = "development"
    description = "Read repositories, READMEs, commits, issues, and pull requests."
    auth_url = "https://github.com/login/oauth/authorize"
    token_url = "https://github.com/login/oauth/access_token"
    api_base_url = "https://api.github.com"

    @property
    def scopes(self) -> list[str]:
        return [scope.strip() for scope in settings.github_scopes_raw.replace(" ", ",").split(",") if scope.strip()]

    @property
    def permissions(self) -> list[str]:
        return ["Repository metadata", "Repository contents", "Issues", "Pull requests", "Profile"]

    @property
    def client_id(self) -> str | None:
        return settings.github_client_id

    @property
    def client_secret(self) -> str | None:
        return settings.github_client_secret

    @property
    def redirect_uri(self) -> str:
        return settings.github_redirect_uri

    def authorization_url(self, *, state: str) -> str:
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": " ".join(self.scopes),
            "state": state,
            "allow_signup": "true",
        }
        return f"{self.auth_url}?{urlencode(params)}"

    def exchange_code(self, code: str) -> TokenPayload:
        with httpx.Client(timeout=20) as client:
            response = client.post(
                self.token_url,
                headers={"Accept": "application/json"},
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "code": code,
                    "redirect_uri": self.redirect_uri,
                },
            )
            response.raise_for_status()
            payload = response.json()
            access_token = payload["access_token"]
            user = client.get(f"{self.api_base_url}/user", headers=self._api_headers(access_token))
            user.raise_for_status()
            emails = client.get(f"{self.api_base_url}/user/emails", headers=self._api_headers(access_token))
            email_payload = emails.json() if emails.status_code < 400 else []
        profile = user.json()
        primary_email = self._primary_email(email_payload) or profile.get("email")
        expires_in = payload.get("expires_in")
        return TokenPayload(
            access_token=access_token,
            refresh_token=payload.get("refresh_token"),
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=int(expires_in)) if expires_in else None,
            provider_account_id=str(profile.get("id") or ""),
            provider_email=primary_email,
            metadata={
                "token_type": payload.get("token_type"),
                "scope": payload.get("scope"),
                "login": profile.get("login"),
                "avatar_url": profile.get("avatar_url"),
                "profile_url": profile.get("html_url"),
            },
        )

    def exchange_refresh_token(self, refresh_token: str) -> TokenPayload:
        with httpx.Client(timeout=20) as client:
            response = client.post(
                self.token_url,
                headers={"Accept": "application/json"},
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                },
            )
            response.raise_for_status()
        payload = response.json()
        expires_in = payload.get("expires_in")
        return TokenPayload(
            access_token=payload["access_token"],
            refresh_token=payload.get("refresh_token") or refresh_token,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=int(expires_in)) if expires_in else None,
            metadata={"token_type": payload.get("token_type"), "scope": payload.get("scope")},
        )

    def disconnect(self, integration: Integration) -> None:
        access_token = integration.access_token
        if access_token and self.client_id and self.client_secret:
            self._revoke_authorization(access_token)
        super().disconnect(integration)

    def get_metadata(self, integration: Integration | None) -> dict:
        if not integration or integration.status != "connected":
            return {"provider": self.id, "status": "not_connected", "items": []}
        headers = self._api_headers(integration.access_token)
        with httpx.Client(timeout=24) as client:
            user_response = client.get(f"{self.api_base_url}/user", headers=headers)
            user_response.raise_for_status()
            repos_response = client.get(
                f"{self.api_base_url}/user/repos",
                headers=headers,
                params={"sort": "updated", "direction": "desc", "per_page": 12, "affiliation": "owner,collaborator,organization_member"},
            )
            repos_response.raise_for_status()
            repos = [self._repo_item(client, headers, repo) for repo in repos_response.json()]
        user_payload = user_response.json()
        return {
            "provider": self.id,
            "status": integration.status,
            "account_email": integration.provider_email,
            "login": user_payload.get("login"),
            "name": user_payload.get("name"),
            "profile_url": user_payload.get("html_url"),
            "items": repos,
            "item_count": len(repos),
            "permissions": self.permissions,
        }

    def _repo_item(self, client: httpx.Client, headers: dict[str, str], repo: dict) -> dict:
        full_name = repo.get("full_name")
        return {
            "id": repo.get("id"),
            "name": repo.get("name"),
            "full_name": full_name,
            "private": repo.get("private"),
            "description": repo.get("description"),
            "language": repo.get("language"),
            "default_branch": repo.get("default_branch"),
            "updated_at": repo.get("updated_at"),
            "url": repo.get("html_url"),
            "readme": self._readme_excerpt(client, headers, full_name),
            "commits": self._recent_items(client, headers, full_name, "commits"),
            "issues": self._recent_items(client, headers, full_name, "issues", params={"state": "open"}),
            "pull_requests": self._recent_items(client, headers, full_name, "pulls", params={"state": "open"}),
        }

    def _readme_excerpt(self, client: httpx.Client, headers: dict[str, str], full_name: str | None) -> str:
        if not full_name:
            return ""
        try:
            response = client.get(f"{self.api_base_url}/repos/{full_name}/readme", headers={**headers, "Accept": "application/vnd.github.raw"})
            if response.status_code >= 400:
                return ""
            return response.text[:1800].strip()
        except Exception:
            return ""

    def _recent_items(self, client: httpx.Client, headers: dict[str, str], full_name: str | None, resource: str, params: dict | None = None) -> list[dict]:
        if not full_name:
            return []
        try:
            response = client.get(f"{self.api_base_url}/repos/{full_name}/{resource}", headers=headers, params={"per_page": 5, **(params or {})})
            if response.status_code >= 400:
                return []
            return [self._compact_item(resource, item) for item in response.json()[:5]]
        except Exception:
            return []

    def _compact_item(self, resource: str, item: dict) -> dict:
        if resource == "commits":
            commit = item.get("commit") or {}
            author = commit.get("author") or {}
            return {"sha": item.get("sha", "")[:8], "message": commit.get("message"), "author": author.get("name"), "date": author.get("date")}
        return {"number": item.get("number"), "title": item.get("title"), "state": item.get("state"), "url": item.get("html_url")}

    def _api_headers(self, access_token: str | None) -> dict[str, str]:
        return {"Authorization": f"Bearer {access_token}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}

    def _revoke_authorization(self, access_token: str) -> None:
        try:
            with httpx.Client(timeout=12) as client:
                response = client.request(
                    "DELETE",
                    f"{self.api_base_url}/applications/{self.client_id}/grant",
                    auth=(self.client_id or "", self.client_secret or ""),
                    headers={"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"},
                    json={"access_token": access_token},
                )
                if response.status_code not in {204, 404, 422}:
                    response.raise_for_status()
        except Exception as exc:
            logger.warning("GitHub authorization revoke failed: %s", repr(exc))

    def _primary_email(self, emails: list[dict]) -> str | None:
        for item in emails:
            if item.get("primary") and item.get("verified"):
                return item.get("email")
        for item in emails:
            if item.get("verified"):
                return item.get("email")
        return None
