from pydantic import BaseModel, Field

from app.schemas.common import TimestampedModel


class FileCreate(BaseModel):
    user_id: str | None = None
    project_id: str | None = None
    name: str = Field(min_length=1, max_length=255)
    file_type: str = Field(min_length=1, max_length=80)
    storage_path: str = Field(min_length=1, max_length=1000)


class FileRead(TimestampedModel):
    user_id: str
    project_id: str | None = None
    name: str
    file_type: str
    storage_path: str
    extraction_metadata: dict = Field(default_factory=dict)


class FileContentRead(FileRead):
    extracted_content: str = ""


class FileProjectUpdate(BaseModel):
    project_id: str | None = None


class DocumentActionRequest(BaseModel):
    action: str = Field(pattern="^(summarize|explain|simple|notes|mcqs|flashcards|actions)$")
    language: str | None = None
    question: str | None = None


class DocumentActionResponse(BaseModel):
    file_id: str
    action: str
    response: str
