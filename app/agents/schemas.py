from __future__ import annotations

from pydantic import BaseModel, Field


class AgentContribution(BaseModel):
    agent: str
    domain: str
    analysis: str
    recommendations: list[str] = Field(default_factory=list)
    frameworks_used: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
