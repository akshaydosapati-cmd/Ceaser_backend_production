from app.services.integrations.base_provider import BaseIntegrationProvider
from app.core.config.settings import settings
from app.models.integration import Integration
import base64
from email.message import EmailMessage


class GmailProvider(BaseIntegrationProvider):
    id = "gmail"
    name = "Gmail"
    category = "productivity"
    description = "Read inbox metadata, unread email, important email, and labels."
    scopes = ["https://www.googleapis.com/auth/gmail.readonly", "https://www.googleapis.com/auth/gmail.metadata", "https://www.googleapis.com/auth/gmail.compose", "https://www.googleapis.com/auth/gmail.send"]
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

    @staticmethod
    def _raw_message(to: str, subject: str, body: str, *, in_reply_to: str | None = None) -> str:
        message = EmailMessage()
        message["To"], message["Subject"] = to, subject
        if in_reply_to:
            message["In-Reply-To"] = in_reply_to
            message["References"] = in_reply_to
        message.set_content(body)
        return base64.urlsafe_b64encode(message.as_bytes()).decode().rstrip("=")

    def create_draft(self, integration: Integration, *, to: str, subject: str, body: str, thread_id: str | None = None, in_reply_to: str | None = None) -> dict:
        payload = {"message": {"raw": self._raw_message(to, subject, body, in_reply_to=in_reply_to)}}
        if thread_id:
            payload["message"]["threadId"] = thread_id
        return self.google_request(integration, "POST", "https://gmail.googleapis.com/gmail/v1/users/me/drafts", payload=payload)

    def update_draft(self, integration: Integration, draft_id: str, *, to: str, subject: str, body: str) -> dict:
        return self.google_request(integration, "PUT", f"https://gmail.googleapis.com/gmail/v1/users/me/drafts/{draft_id}", payload={"message": {"raw": self._raw_message(to, subject, body)}})

    def send_draft(self, integration: Integration, draft_id: str) -> dict:
        return self.google_request(integration, "POST", "https://gmail.googleapis.com/gmail/v1/users/me/drafts/send", payload={"id": draft_id})
