from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class DraftCreate(BaseModel):
    user_id: str | None = None
    prompt: str = Field(min_length=1)
    draft_type: str | None = None
    agent_id: str | None = None
    target_app: str = "keep_as_draft"
    requested_units: int = Field(default=8, ge=1, le=100)


class DraftRead(BaseModel):
    id: str
    user_id: str
    agent_id: str
    title: str
    draft_type: str
    status: str
    progress: int
    target_app: str
    requested_units: int
    source_prompt: str
    content: dict
    created_at: datetime


class DraftHistoryRead(BaseModel):
    id: str
    draft_id: str
    user_id: str
    agent_id: str
    action: str
    detail: str
    created_at: datetime


class AgentWorkbenchRead(BaseModel):
    agent_id: str
    kpis: dict
    quick_actions: list[str]
    templates: list[dict]
    drafts: list[DraftRead]
    activity: list[DraftHistoryRead]
