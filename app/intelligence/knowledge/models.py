from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ContextKind(StrEnum):
    DOCUMENT_CHUNK = "document_chunk"
    FILE = "file"
    MEMORY = "memory"
    PROJECT = "project"
    EMAIL = "email"
    CALENDAR_EVENT = "calendar_event"
    DRIVE_FILE = "drive_file"
    WEB_RESULT = "web_result"
    WEATHER = "weather"
    NEWS = "news"
    WORKFLOW_RESULT = "workflow_result"
    GENERATED_ARTIFACT = "generated_artifact"


@dataclass(slots=True)
class ContextItem:
    id: str
    provider: str
    kind: ContextKind
    content: str
    title: str | None = None
    source_uri: str | None = None
    source_id: str | None = None
    chunk_id: str | None = None
    relevance_score: float = 0.0
    freshness_score: float = 0.0
    authority_score: float = 0.0
    permissions: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ContextPackage:
    items: list[ContextItem]
    evidence_text: str
    token_budget: int = 6000

    def to_prompt(self, message: str) -> str:
        if not self.evidence_text:
            return message
        return f"User request:\n{message}\n\nRelevant CEASER evidence:\n{self.evidence_text}"

