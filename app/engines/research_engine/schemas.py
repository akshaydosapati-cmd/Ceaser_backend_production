from __future__ import annotations

from pydantic import BaseModel, Field


class ResearchRequest(BaseModel):
    query: str = Field(min_length=1)


class ResearchSource(BaseModel):
    title: str
    url: str
    source: str
    snippet: str
    score: float = 0


class Citation(BaseModel):
    title: str
    url: str


class ResearchResult(BaseModel):
    query: str
    summary: str
    key_findings: list[str]
    sources: list[ResearchSource]
    citations: list[Citation]
