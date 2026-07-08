from pydantic import BaseModel, Field

from app.schemas.common import TimestampedModel


class MemoryCreate(BaseModel):
    user_id: str | None = None
    memory_type: str = Field(pattern="^(conversation|goal|project|decision|file|research)$")
    content: str = Field(min_length=1)
    metadata: dict = Field(default_factory=dict)


class MemorySearch(BaseModel):
    user_id: str | None = None
    query: str = ""


class MemoryRead(TimestampedModel):
    user_id: str
    memory_type: str
    content: str
    metadata: dict = Field(default_factory=dict, alias="extra_metadata")
