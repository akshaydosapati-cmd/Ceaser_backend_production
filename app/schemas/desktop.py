from __future__ import annotations

from pydantic import BaseModel, Field


class DesktopIntentRequest(BaseModel):
    command: str = Field(min_length=1)
    user_id: str | None = None


class DesktopIntentResponse(BaseModel):
    intent: str
    intent_type: str | None = None
    action: str
    parameters: dict = Field(default_factory=dict)
    requires_confirmation: bool = False
    requires_permission: bool = False
    required_permission: str | None = None
    risk_level: str = "low"
    active_agent: str | None = None
    agent_action: str | None = None
    overlay_mode: str = "compact"
    overlay_state: str = "thinking"
    progress_steps: list[dict] = Field(default_factory=list)
    result_preview: dict = Field(default_factory=dict)
