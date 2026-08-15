from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class DeviceCapabilityRequest(BaseModel):
    request_id: str
    task_id: str
    agent_id: str
    device_id: str
    capability: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    confirmation_requirement: Literal["none", "required", "already_confirmed"] = "none"
    timeout_seconds: int = Field(default=30, ge=1, le=300)
    authorization: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DeviceCapabilityResult(BaseModel):
    request_id: str
    status: Literal["completed", "failed", "timeout", "cancelled"]
    output: dict[str, Any] = Field(default_factory=dict)
    error: dict[str, Any] | None = None
    verification: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
