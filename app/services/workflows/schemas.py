from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Any, Literal


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


class UserGoal(BaseModel):
    goal_id: str
    user_id: str
    original_request: str
    inferred_outcome: str
    active_project: str | None = None
    relevant_context: dict[str, Any] = Field(default_factory=dict)
    known_files: list[str] = Field(default_factory=list)
    available_integrations: list[str] = Field(default_factory=list)
    available_devices: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    required_confirmations: list[str] = Field(default_factory=list)
    requested_deadline: str | None = None
    current_conversation: str | None = None
    relevant_memory: dict[str, Any] = Field(default_factory=dict)


class GoalWorkflowStep(BaseModel):
    step_id: str
    capability: str
    responsible_agent: str | None = None
    execution_target: str
    input_refs: list[str] = Field(default_factory=list)
    output_name: str
    depends_on: list[str] = Field(default_factory=list)
    confirmation_required: bool = False
    verification_rule: str
    retry_limit: int = Field(default=1, ge=0, le=2)
    failure_strategy: Literal["stop", "replan", "wait_for_user"] = "replan"


class GoalWorkflowPlan(BaseModel):
    workflow_id: str
    goal: UserGoal
    steps: list[GoalWorkflowStep]
    state: Literal["PLANNED", "WAITING_FOR_USER", "WAITING_FOR_DEVICE", "FAILED"] = "PLANNED"
    estimated_credits: int = 0
    missing_capabilities: list[str] = Field(default_factory=list)
