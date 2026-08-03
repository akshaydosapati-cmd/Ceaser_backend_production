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


class ProjectMemberCreate(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    name: str | None = Field(default=None, max_length=255)
    role: str = Field(default="viewer", pattern="^(owner|admin|editor|viewer)$")
    status: str = Field(default="invited", pattern="^(active|invited|removed)$")


class ProjectMemberUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    role: str | None = Field(default=None, pattern="^(owner|admin|editor|viewer)$")
    status: str | None = Field(default=None, pattern="^(active|invited|removed)$")


class ProjectMemberRead(TimestampedModel):
    project_id: str
    user_id: str | None = None
    email: str
    name: str | None = None
    role: str
    status: str
