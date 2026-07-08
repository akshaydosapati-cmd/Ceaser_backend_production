from __future__ import annotations

from pydantic import BaseModel, Field


class WorkflowTemplate(BaseModel):
    id: str
    name: str
    description: str
    agents: list[str]
    mode: str = "sequential"


class WorkflowPlan(BaseModel):
    workflow_type: str
    name: str
    agents: list[str]
    mode: str = "sequential"
    reason: str


class WorkflowExecutionResult(BaseModel):
    workflow_id: str
    workflow_type: str
    status: str
    selected_agents: list[str]
    contributions: list[dict] = Field(default_factory=list)
    final_response: str
    result_summary: str
    steps: list[dict] = Field(default_factory=list)
