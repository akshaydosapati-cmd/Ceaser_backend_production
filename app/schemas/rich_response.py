from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, HttpUrl, model_validator

ResponseStatus = Literal["streaming", "working", "waiting_for_user", "waiting_for_confirmation", "completed", "partial", "failed", "cancelled"]
BlockType = Literal["text", "markdown", "code", "table", "image", "image_group", "generated_image", "file", "chart", "source_group", "project", "status", "action", "error"]

class ResponseSource(BaseModel):
    source_id: str = Field(default_factory=lambda: f"src_{uuid4().hex}")
    title: str
    url: HttpUrl
    domain: str
    publisher: str | None = None
    snippet: str | None = None

class ResponseAction(BaseModel):
    action_id: str = Field(default_factory=lambda: f"act_{uuid4().hex}")
    label: str
    capability: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    requires_confirmation: bool = False
    enabled: bool = True

class ResponseAsset(BaseModel):
    asset_id: str
    user_id: str = Field(exclude=True)
    filename: str
    mime_type: str
    size: int = Field(ge=0)
    reference: str
    origin: Literal["uploaded", "generated", "cloud", "device", "project"]
    device_id: str | None = None
    status: str = "available"

class ResponseBlock(BaseModel):
    block_id: str = Field(default_factory=lambda: f"blk_{uuid4().hex}")
    type: BlockType
    content: str | None = None
    language: str | None = None
    filename: str | None = None
    columns: list[str] = Field(default_factory=list)
    rows: list[list[Any]] = Field(default_factory=list)
    caption: str | None = None
    chart_type: Literal["line", "bar", "pie", "area"] | None = None
    title: str | None = None
    labels: list[str] = Field(default_factory=list)
    series: list[dict[str, Any]] = Field(default_factory=list)
    url: HttpUrl | None = None
    thumbnail_url: HttpUrl | None = None
    source_url: HttpUrl | None = None
    source_name: str | None = None
    alt_text: str | None = None
    width: int | None = Field(default=None, ge=1)
    height: int | None = Field(default=None, ge=1)
    asset_id: str | None = None
    project: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    actions: list[ResponseAction] = Field(default_factory=list)
    items: list[dict[str, Any]] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_structured_data(self):
        if self.type == "table" and (not self.columns or any(len(row) != len(self.columns) for row in self.rows)):
            raise ValueError("table rows must match columns")
        if self.type == "chart" and (not self.chart_type or not self.labels or not self.series):
            raise ValueError("chart requires chart_type, labels and series")
        if self.type == "image" and not self.source_url:
            raise ValueError("web images require a real source_url")
        return self

class ActivityEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: f"evt_{uuid4().hex}")
    task_id: str
    agent: str = "CEASER"
    category: str
    stage: str
    status: Literal["pending", "running", "waiting", "completed", "failed", "cancelled"]
    title: str
    detail: str | None = None
    progress: int | None = Field(default=None, ge=0, le=100)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    safe_metadata: dict[str, Any] = Field(default_factory=dict)

class CeaserRichResponse(BaseModel):
    id: str = Field(default_factory=lambda: f"resp_{uuid4().hex}")
    conversation_id: str | None = None
    message_id: str | None = None
    status: ResponseStatus = "completed"
    primary_text: str
    blocks: list[ResponseBlock] = Field(default_factory=list)
    sources: list[ResponseSource] = Field(default_factory=list)
    assets: list[ResponseAsset] = Field(default_factory=list)
    actions: list[ResponseAction] = Field(default_factory=list)
    activity: list[ActivityEvent] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
