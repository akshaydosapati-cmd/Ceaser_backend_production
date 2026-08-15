from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class RoutingPolicy(str, Enum):
    BALANCED = "balanced"
    FAST = "fast"
    QUALITY = "quality"
    ECONOMY = "economy"


class Workload(str, Enum):
    NORMAL_CHAT = "normal_chat"
    SPECIALIST = "specialist"
    SOFTWARE_ENGINEERING = "software_engineering"


class HealthState(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    COOLDOWN = "cooldown"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


class FailureCategory(str, Enum):
    TIMEOUT = "timeout"
    RATE_LIMIT = "rate_limit"
    AUTHENTICATION = "authentication"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    INVALID_REQUEST = "invalid_request"
    CONTEXT_TOO_LARGE = "context_too_large"
    MODEL_UNAVAILABLE = "model_unavailable"
    NETWORK_ERROR = "network_error"
    UNKNOWN = "unknown"


class ModelDefinition(BaseModel):
    model_id: str
    provider_id: str
    provider_model_name: str
    display_name: str
    enabled: bool = True
    available: bool = True
    capabilities: frozenset[str]
    allowed_workloads: frozenset[Workload] = frozenset(
        {Workload.NORMAL_CHAT, Workload.SPECIALIST, Workload.SOFTWARE_ENGINEERING}
    )
    context_window: int = Field(gt=0)
    supports_tools: bool = False
    supports_streaming: bool = True
    supports_vision: bool = False
    relative_speed: int = Field(default=5, ge=1, le=10)
    relative_quality: int = Field(default=5, ge=1, le=10)
    relative_cost: int = Field(default=5, ge=1, le=10)
    priority: int = 0
    tags: tuple[str, ...] = ()
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_identity(self):
        if not self.model_id.strip() or not self.provider_id.strip() or not self.provider_model_name.strip():
            raise ValueError("model and provider identities are required")
        return self

    def safe_metadata(self) -> dict[str, Any]:
        return self.model_dump(exclude={"metadata"}) | {"metadata": {k: v for k, v in self.metadata.items() if "key" not in k.lower() and "secret" not in k.lower()}}


class ModelRequest(BaseModel):
    request_id: str
    task_type: str = "general"
    workload: Workload = Workload.NORMAL_CHAT
    required_capabilities: frozenset[str] = frozenset({"general"})
    preferred_capabilities: frozenset[str] = frozenset()
    context_size_estimate: int = Field(default=0, ge=0)
    needs_tools: bool = False
    needs_vision: bool = False
    needs_streaming: bool = False
    latency_preference: int = Field(default=5, ge=1, le=10)
    quality_preference: int = Field(default=5, ge=1, le=10)
    cost_preference: int = Field(default=5, ge=1, le=10)
    policy: RoutingPolicy = RoutingPolicy.BALANCED
    agent_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SelectedModel(BaseModel):
    request_id: str
    model: ModelDefinition
    score: float
    reason: str


class ModelResponse(BaseModel):
    content: str
    provider_id: str
    model_id: str
    latency_ms: float
    usage: dict[str, Any] | None = None
    status: str = "completed"
    finish_reason: str | None = None
    fallback_used: bool = False
    attempt_count: int = 1
    routing_metadata: dict[str, Any] = Field(default_factory=dict)


class ModelEvent(BaseModel):
    event: str
    request_id: str
    metadata: dict[str, Any] = Field(default_factory=dict)
