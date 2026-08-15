from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.agents.v2.models import ExecutionTarget


class PlacementPolicy(str, Enum):
    LOCAL_FIRST = "LOCAL_FIRST"
    CLOUD_FIRST = "CLOUD_FIRST"
    AUTO = "AUTO"


class PlacementFailure(str, Enum):
    NO_DEVICE = "no_device"
    DEVICE_OFFLINE = "device_offline"
    DEVICE_UNAUTHORIZED = "device_unauthorized"
    CAPABILITY_UNAVAILABLE = "capability_unavailable"
    CLOUD_UNAVAILABLE = "cloud_unavailable"
    PROJECT_NOT_AVAILABLE = "project_not_available"
    NO_COMPATIBLE_TARGET = "no_compatible_target"
    CONFIRMATION_REQUIRED = "confirmation_required"
    TIMEOUT = "timeout"
    CLOUD_CODING_DISABLED = "cloud_coding_disabled"
    AMBIGUOUS_DEVICE = "ambiguous_device"


class ProjectExecutionContext(BaseModel):
    project_id: str | None = None
    local_path: str | None = None
    cloud_workspace_id: str | None = None
    git_repository: str | None = None
    device_id: str | None = None
    synchronized: bool | None = None


class DeviceAvailability(BaseModel):
    device_id: str
    user_id: str
    connected: bool = False
    authenticated: bool = False
    authorized: bool = False
    advertised_capabilities: frozenset[str] = Field(default_factory=frozenset)
    preferred: bool = False


class CloudAvailability(BaseModel):
    available: bool = False
    advertised_capabilities: frozenset[str] = Field(default_factory=frozenset)


class ExecutionRequest(BaseModel):
    request_id: str
    task_id: str
    agent_id: str
    capability: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    required_target: ExecutionTarget = ExecutionTarget.EITHER
    preferred_target: ExecutionTarget | None = None
    user_id: str
    device_id: str | None = None
    requires_confirmation: bool = False
    confirmed: bool = False
    timeout_seconds: int = Field(default=30, ge=1, le=300)
    resource_requirements: dict[str, Any] = Field(default_factory=dict)
    project_context: ProjectExecutionContext | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExecutionDecision(BaseModel):
    request_id: str
    task_id: str
    target: ExecutionTarget
    reason: str
    device_id: str | None = None
    fallback_target: ExecutionTarget | None = None
    can_execute_now: bool = False
    requires_wait: bool = False
    requires_sync: bool = False
    requires_confirmation: bool = False
    failure: PlacementFailure | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExecutionResult(BaseModel):
    request_id: str
    task_id: str
    target_used: ExecutionTarget
    executor: str
    status: Literal["completed", "failed", "timeout", "cancelled", "deferred"]
    output: dict[str, Any] = Field(default_factory=dict)
    error: dict[str, Any] | None = None
    verification: dict[str, Any] = Field(default_factory=dict)
    duration_ms: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExecutionPlacementEvent(BaseModel):
    event: str
    task_id: str
    agent_id: str
    capability: str
    target: ExecutionTarget | None = None
    reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
