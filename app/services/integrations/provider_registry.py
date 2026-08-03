from __future__ import annotations

from app.services.integrations.base_provider import BaseIntegrationProvider
from app.services.integrations.gmail_provider import GmailProvider
from app.services.integrations.google_calendar_provider import GoogleCalendarProvider
from app.services.integrations.google_classroom_provider import GoogleClassroomProvider
from app.services.integrations.google_drive_provider import GoogleDriveProvider
from app.services.integrations.google_tasks_provider import GoogleTasksProvider
from app.services.integrations.github_provider import GitHubProvider
from app.services.integrations.notion_provider import NotionProvider


class ProviderRegistry:
    def __init__(self) -> None:
        providers: list[BaseIntegrationProvider] = [
            GoogleCalendarProvider(),
            GmailProvider(),
            GoogleDriveProvider(),
            GoogleTasksProvider(),
            GoogleClassroomProvider(),
            NotionProvider(),
            GitHubProvider(),
        ]
        self.providers = {provider.id: provider for provider in providers}

    def list(self) -> list[BaseIntegrationProvider]:
        return list(self.providers.values())

    def get(self, provider_id: str) -> BaseIntegrationProvider:
        provider = self.providers.get(provider_id)
        if not provider:
            raise ValueError(f"Unsupported integration provider: {provider_id}")
        return provider
