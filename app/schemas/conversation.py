from pydantic import BaseModel, Field

from app.schemas.common import TimestampedModel


class ConversationCreate(BaseModel):
    user_id: str | None = None
    title: str | None = Field(default=None, min_length=1, max_length=255)


class ConversationRead(TimestampedModel):
    user_id: str
    title: str
    pinned: bool = False
    archived: bool = False
    conversation_summary: str | None = None
    conversation_state: dict = Field(default_factory=dict)
    summary_version: int = 1


class ConversationUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    pinned: bool | None = None
    archived: bool | None = None


class MessageCreate(BaseModel):
    conversation_id: str | None = None
    role: str = Field(pattern="^(user|assistant|system)$", default="user")
    content: str = Field(min_length=1)
    metadata: dict = Field(default_factory=dict)


class MessageRead(TimestampedModel):
    conversation_id: str
    role: str
    content: str
    metadata: dict = Field(default_factory=dict, validation_alias="extra_metadata", serialization_alias="metadata")
