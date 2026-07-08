from pydantic import BaseModel, Field

from app.schemas.common import TimestampedModel


class ProjectCreate(BaseModel):
    user_id: str | None = None
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    status: str = Field(default="planned", pattern="^(planned|active|completed|archived)$")


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    status: str | None = Field(default=None, pattern="^(planned|active|completed|archived)$")


class ProjectRead(TimestampedModel):
    user_id: str
    name: str
    description: str | None = None
    status: str
