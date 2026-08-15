from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class ExecutionTarget(str, Enum):
    DEVICE = "DEVICE"
    CLOUD = "CLOUD"
    EITHER = "EITHER"
    NONE = "NONE"


class AgentTaskStatus(str, Enum):
    CREATED = "created"
    PLANNING = "planning"
    RUNNING = "running"
    WAITING_FOR_DEVICE = "waiting_for_device"
    WAITING_FOR_CLOUD = "waiting_for_cloud"
    WAITING_FOR_CONFIRMATION = "waiting_for_confirmation"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AgentDefinition(BaseModel):
    id: str
    name: str
    role: str
    description: str
    instructions: str
    task_categories: tuple[str, ...]
    allowed_capability_categories: tuple[str, ...]
    denied_capability_categories: tuple[str, ...] = ()
    memory_context_scope: tuple[str, ...] = ("conversation", "active_project")
    planning_policy: str = "bounded"
    confirmation_policy: str = "inherit_capability_policy"
    verification_policy: str = "evidence_required"
    model_requirements: tuple[str, ...] = ("reasoning",)
    delegation_policy: tuple[str, ...] = ()
    execution_requirements: tuple[ExecutionTarget, ...] = (ExecutionTarget.NONE,)
    enabled: bool = True

    def permits(self, capability: str) -> bool:
        category = capability.split(".", 1)[0].lower()
        denied = {item.lower() for item in self.denied_capability_categories}
        allowed = {item.lower() for item in self.allowed_capability_categories}
        return category not in denied and (category in allowed or "*" in allowed)


class AgentSelection(BaseModel):
    route: str
    agent_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0, le=1)
    reason: str
    execution_target: ExecutionTarget = ExecutionTarget.NONE


class VerificationEvidence(BaseModel):
    verified: bool = False
    checks: list[dict[str, Any]] = Field(default_factory=list)
    summary: str = ""


class AgentResult(BaseModel):
    task_id: str
    agent_id: str
    status: AgentTaskStatus
    summary: str
    outputs: list[dict[str, Any]] = Field(default_factory=list)
    actions_taken: list[dict[str, Any]] = Field(default_factory=list)
    execution_targets_used: list[ExecutionTarget] = Field(default_factory=list)
    capabilities_used: list[str] = Field(default_factory=list)
    files_changed: list[str] = Field(default_factory=list)
    verification: VerificationEvidence = Field(default_factory=VerificationEvidence)
    blockers: list[str] = Field(default_factory=list)
    next_action: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def completed_requires_verification(self):
        if self.status == AgentTaskStatus.COMPLETED and not self.verification.verified:
            raise ValueError("completed agent results require verified evidence")
        return self


class AgentEvent(BaseModel):
    event: str
    task_id: str
    agent_id: str | None = None
    status: AgentTaskStatus | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
