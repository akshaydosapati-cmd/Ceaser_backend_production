from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class TemplateRead(BaseModel):
    id: str
    name: str
    kind: str
    agent_id: str
    sections: list[str]


class GenerateDocumentRequest(BaseModel):
    user_id: str | None = None
    prompt: str = Field(min_length=1)
    kind: str = Field(pattern="^(docx|pdf|pptx|xlsx)$")
    template_id: str | None = None
    agent_id: str | None = None


class GeneratedDocumentRead(BaseModel):
    id: str
    file_id: str
    user_id: str
    agent_id: str
    template_id: str
    generated_by: str
    export_format: str
    version: int
    source_prompt: str
    created_at: datetime
    file_name: str | None = None


class GenerateDocumentResponse(BaseModel):
    document: GeneratedDocumentRead
    file: dict
    preview: str


class AgentActivityRead(BaseModel):
    id: str
    user_id: str
    file_id: str | None = None
    agent_id: str
    action: str
    detail: str
    created_at: datetime
