from __future__ import annotations

from pydantic import BaseModel, Field


class DocumentTemplate(BaseModel):
    id: str
    name: str
    kind: str
    agent_id: str
    sections: list[str]


class GeneratedDocumentResult(BaseModel):
    title: str
    kind: str
    content: str
    bytes_data: bytes = Field(exclude=True)
    content_type: str
    filename: str
    template: DocumentTemplate
    agent_id: str
