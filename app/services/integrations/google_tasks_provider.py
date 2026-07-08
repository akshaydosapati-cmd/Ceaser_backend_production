from app.services.integrations.base_provider import BaseIntegrationProvider
from app.core.config.settings import settings
from app.models.integration import Integration


class GoogleTasksProvider(BaseIntegrationProvider):
    id = "google-tasks"
    name = "Google Tasks"
    category = "productivity"
    description = "Read task lists, tasks, and due dates."
    scopes = ["https://www.googleapis.com/auth/tasks.readonly"]
    auth_url = "https://accounts.google.com/o/oauth2/v2/auth"
    token_url = "https://oauth2.googleapis.com/token"

    @property
    def redirect_uri(self) -> str:
        return settings.google_tasks_oauth_redirect_uri

    def get_metadata(self, integration: Integration | None) -> dict:
        if not integration or integration.status != "connected":
            return {"provider": self.id, "status": "not_connected", "items": []}
        lists_payload = self.google_get(integration, "https://tasks.googleapis.com/tasks/v1/users/@me/lists", {"maxResults": 10})
        tasks = []
        for task_list in lists_payload.get("items", [])[:6]:
            tasks_payload = self.google_get(
                integration,
                f"https://tasks.googleapis.com/tasks/v1/lists/{task_list.get('id')}/tasks",
                {"maxResults": 10, "showCompleted": "false"},
            )
            for task in tasks_payload.get("items", [])[:10]:
                tasks.append(
                    {
                        "id": task.get("id"),
                        "title": task.get("title"),
                        "status": task.get("status"),
                        "due": task.get("due"),
                        "updated": task.get("updated"),
                        "list": task_list.get("title"),
                        "notes": task.get("notes"),
                    }
                )
        return {
            "provider": self.id,
            "status": integration.status,
            "account_email": integration.provider_email,
            "permissions": self.permissions,
            "summary": {
                "task_lists": len(lists_payload.get("items", [])),
                "open_tasks": len(tasks),
            },
            "items": tasks[:30],
        }
