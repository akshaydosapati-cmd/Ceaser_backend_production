from __future__ import annotations

from pydantic import BaseModel, Field


class ExtractedDocument(BaseModel):
    title: str
    pages: int = 1
    content: str
    metadata: dict = Field(default_factory=dict)
