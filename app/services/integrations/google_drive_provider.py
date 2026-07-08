from app.services.integrations.base_provider import BaseIntegrationProvider
from app.core.config.settings import settings
from app.models.integration import Integration


class GoogleDriveProvider(BaseIntegrationProvider):
    id = "google-drive"
    name = "Google Drive"
    category = "productivity"
    description = "Read Drive file metadata and supported document content."
    scopes = ["https://www.googleapis.com/auth/drive.readonly", "https://www.googleapis.com/auth/drive.metadata.readonly"]
    auth_url = "https://accounts.google.com/o/oauth2/v2/auth"
    token_url = "https://oauth2.googleapis.com/token"

    @property
    def redirect_uri(self) -> str:
        return settings.google_drive_oauth_redirect_uri

    def get_metadata(self, integration: Integration | None) -> dict:
        if not integration or integration.status != "connected":
            return {"provider": self.id, "status": "not_connected", "items": []}
        files_payload = self.google_get(
            integration,
            "https://www.googleapis.com/drive/v3/files",
            {
                "pageSize": 12,
                "orderBy": "modifiedTime desc",
                "fields": "files(id,name,mimeType,modifiedTime,webViewLink,size,owners(displayName,emailAddress))",
            },
        )
        files = [
            {
                "id": item.get("id"),
                "name": item.get("name"),
                "mime_type": item.get("mimeType"),
                "modified_time": item.get("modifiedTime"),
                "link": item.get("webViewLink"),
                "size": item.get("size"),
                "owner": (item.get("owners") or [{}])[0].get("emailAddress"),
            }
            for item in files_payload.get("files", [])
        ]
        return {
            "provider": self.id,
            "status": integration.status,
            "account_email": integration.provider_email,
            "permissions": self.permissions,
            "summary": {
                "recent_files": len(files),
                "document_files": sum(1 for item in files if "document" in str(item.get("mime_type", ""))),
                "spreadsheet_files": sum(1 for item in files if "spreadsheet" in str(item.get("mime_type", ""))),
            },
            "items": files,
        }
