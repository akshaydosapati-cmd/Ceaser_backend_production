from __future__ import annotations

from pydantic import BaseModel


class AutomationExecutionResult(BaseModel):
    title: str
    summary: str
    content: str
    metadata: dict
