from app.services.integrations.base_provider import BaseIntegrationProvider
from app.core.config.settings import settings
from app.models.integration import Integration


class GmailProvider(BaseIntegrationProvider):
    id = "gmail"
    name = "Gmail"
    category = "productivity"
    description = "Read inbox metadata, unread email, important email, and labels."
    scopes = ["https://www.googleapis.com/auth/gmail.readonly", "https://www.googleapis.com/auth/gmail.metadata"]
    auth_url = "https://accounts.google.com/o/oauth2/v2/auth"
    token_url = "https://oauth2.googleapis.com/token"

    @property
    def redirect_uri(self) -> str:
        return settings.google_gmail_oauth_redirect_uri

    def get_metadata(self, integration: Integration | None) -> dict:
        if not integration or integration.status != "connected":
            return {"provider": self.id, "status": "not_connected", "items": []}
        profile = self._safe_google_get(integration, "https://gmail.googleapis.com/gmail/v1/users/me/profile")
        labels_payload = self._safe_google_get(integration, "https://gmail.googleapis.com/gmail/v1/users/me/labels")
        messages_payload = self._safe_google_get(
            integration,
            "https://gmail.googleapis.com/gmail/v1/users/me/messages",
            {"maxResults": 8, "q": "newer_than:14d"},
        )
        if not messages_payload.get("messages"):
            messages_payload = self._safe_google_get(
                integration,
                "https://gmail.googleapis.com/gmail/v1/users/me/messages",
                {"maxResults": 8},
            )
        messages = []
        for message in messages_payload.get("messages", [])[:8]:
            detail = self._safe_google_get(
                integration,
                f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{message.get('id')}",
                {"format": "metadata", "metadataHeaders": ["From", "Subject", "Date"]},
            )
            if not detail:
                continue
            headers = {header.get("name", "").lower(): header.get("value") for header in detail.get("payload", {}).get("headers", [])}
            messages.append(
                {
                    "id": detail.get("id"),
                    "from": headers.get("from"),
                    "subject": headers.get("subject") or "(No subject)",
                    "date": headers.get("date"),
                    "snippet": detail.get("snippet"),
                }
            )
        labels = labels_payload.get("labels", [])
        return {
            "provider": self.id,
            "status": integration.status,
            "account_email": integration.provider_email or profile.get("emailAddress"),
            "permissions": self.permissions,
            "summary": {
                "email": profile.get("emailAddress"),
                "message_count_estimate": profile.get("messagesTotal"),
                "thread_count_estimate": profile.get("threadsTotal"),
                "label_count": len(labels),
                "recent_messages": len(messages),
            },
            "items": messages,
            "labels": [{"id": label.get("id"), "name": label.get("name"), "type": label.get("type")} for label in labels[:20]],
        }

    def _safe_google_get(self, integration: Integration, url: str, params: dict | None = None) -> dict:
        try:
            return self.google_get(integration, url, params)
        except Exception as exc:
            return {"error": str(exc)}
