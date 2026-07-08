from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DraftSection(BaseModel):
    title: str
    body: str = ""
    status: str = "draft"


class DraftContent(BaseModel):
    model_config = ConfigDict(extra="allow")

    title: str
    type: str
    owner_agent: str
    sections: list[dict[str, Any]] = Field(default_factory=list)


class DraftTemplate(BaseModel):
    id: str
    name: str
    draft_type: str
    agent_id: str
    sections: list[str]
