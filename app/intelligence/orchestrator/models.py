from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class IntentType(StrEnum):
    GENERAL_QUESTION = "general_question"
    FILE_LOOKUP = "file_lookup"
    FILE_SUMMARY = "file_summary"
    PROJECT_QUESTION = "project_question"
    MEMORY_QUESTION = "memory_question"
    DOCUMENT_GENERATION = "document_generation"
    RESEARCH = "research"
    EMAIL_DRAFT = "email_draft"
    EMAIL_SEND = "email_send"
    CALENDAR_LOOKUP = "calendar_lookup"
    CALENDAR_CREATE = "calendar_create"
    DESKTOP_ACTION = "desktop_action"
    WORKFLOW = "workflow"


@dataclass(slots=True)
class RequestContext:
    user_id: str
    message: str
    conversation_id: str | None = None
    organization_id: str | None = None
    workspace_id: str | None = None
    project_id: str | None = None
    source_id: str | None = None
    subject_id: str | None = None
    career_profile_id: str | None = None
    active_screen: str | None = None
    active_file_path: str | None = None
    selected_file_ids: list[str] = field(default_factory=list)
    interaction_mode: str = "chat"
    locale: str = "en"
    timezone: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ProviderPlan:
    provider: str
    query: str
    required: bool = False
    filters: dict[str, Any] = field(default_factory=dict)
    limit: int = 10


@dataclass(slots=True)
class RetrievalPlan:
    intent: IntentType
    providers: list[ProviderPlan]
    needs_generation: bool
    output_format: str
    requires_confirmation: bool = False
    retrieval_scope: str = "mixed"

    @property
    def retrieval_sources(self) -> list[str]:
        return [provider.provider for provider in self.providers]
