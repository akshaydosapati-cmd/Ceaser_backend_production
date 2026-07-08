from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import TimestampedModel


class WorkflowStartRequest(BaseModel):
    message: str = Field(min_length=1)
    conversation_id: str | None = None
    file_ids: list[str] = Field(default_factory=list)


class WorkflowTemplateRead(BaseModel):
    id: str
    name: str
    description: str
    agents: list[str]
    mode: str


class WorkflowStepRead(BaseModel):
    id: str
    workflow_id: str
    agent_name: str
    status: str
    started_at: datetime | None = None
    completed_at: datetime | None = None
    output_summary: str | None = None
    metadata_json: dict = Field(default_factory=dict)

    model_config = {"from_attributes": True}


class WorkflowRunRead(TimestampedModel):
    user_id: str
    workspace_id: str | None = None
    workflow_type: str
    status: str
    started_at: datetime | None = None
    completed_at: datetime | None = None
    result_summary: str | None = None
    metadata_json: dict = Field(default_factory=dict)
    updated_at: datetime


class WorkflowStartResponse(BaseModel):
    workflow_id: str
    workflow_type: str
    status: str
    selected_agents: list[str]
    contributions: list[dict]
    final_response: str
    result_summary: str
    steps: list[dict]
