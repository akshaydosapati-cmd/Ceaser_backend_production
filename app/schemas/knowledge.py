from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class KnowledgeSourceRead(BaseModel):
    id: str
    title: str
    source_type: str
    status: str
    project_id: str | None = None
    conversation_id: str | None = None
    indexed_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class KnowledgeChunkRead(BaseModel):
    id: str
    source_id: str
    title: str | None = None
    content: str
    section_title: str | None = None
    relevance_score: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgeIngestTextRequest(BaseModel):
    title: str
    content: str
    source_type: str = "note"
    project_id: str | None = None
    conversation_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgeSearchRequest(BaseModel):
    query: str
    project_id: str | None = None
    source_id: str | None = None
    limit: int = Field(default=8, ge=1, le=30)


class KnowledgeSearchResponse(BaseModel):
    items: list[KnowledgeChunkRead]
    provider_names: list[str]
    latency_ms: int


class ContextBuildRequest(BaseModel):
    message: str
    project_id: str | None = None
    conversation_id: str | None = None
    active_screen: str | None = None
    interaction_mode: str = "chat"
    limit: int = Field(default=8, ge=1, le=30)


class ContextBuildResponse(BaseModel):
    intent: str
    output_format: str
    needs_generation: bool
    evidence_text: str
    items: list[KnowledgeChunkRead]

