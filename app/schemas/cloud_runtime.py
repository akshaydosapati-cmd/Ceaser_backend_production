from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CloudJobCreate(BaseModel):
    agent_id: str = Field(max_length=80)
    task_id: str = Field(max_length=120)
    request_id: str = Field(max_length=120)
    capability: str = Field(max_length=160)
    arguments: dict[str, Any] = Field(default_factory=dict)
    project_id: str | None = None
    parent_job_id: str | None = None
    idempotency_key: str | None = Field(default=None, max_length=160)
    requires_confirmation: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class CloudJobResume(BaseModel):
    approved: bool
    response: str | None = Field(default=None, max_length=1000)


class CloudJobRead(BaseModel):
    id: str
    task_id: str
    request_id: str
    agent_id: str
    capability: str
    status: str
    execution_target: str
    workspace_id: str | None
    current_step: str | None
    progress: float
    attempt_count: int
    max_attempts: int
    result_summary: str | None
    failure_category: str | None
    safe_error: str | None
    pending_action: dict[str, Any] | None
    created_at: Any
    started_at: Any = None
    updated_at: Any = None
    completed_at: Any = None
    cancelled_at: Any = None


class CloudJobAccepted(BaseModel):
    job_id: str
    task_id: str
    workspace_id: str
    status: str
    created_at: Any
