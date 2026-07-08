from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import TimestampedModel


AutomationType = "^(research|news|business|content|learning|execution|engineering)$"
AutomationFrequency = "^(once|daily|weekly|monthly|every_weekday|custom)$"
AutomationStatus = "^(active|paused)$"


class AutomationTemplateRead(BaseModel):
    id: str
    name: str
    category: str
    description: str
    default_agent: str
    default_prompt: str
    supported_frequencies: list[str]
    icon: str
    is_active: bool = True


class AutomationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    automation_type: str = Field(pattern=AutomationType)
    trigger_frequency: str = Field(default="daily", pattern=AutomationFrequency)
    trigger_time: str | None = "morning"
    timezone: str = "UTC"
    status: str = Field(default="active", pattern=AutomationStatus)
    config_json: dict = Field(default_factory=dict)
    workspace_id: str | None = None


class AutomationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    automation_type: str | None = Field(default=None, pattern=AutomationType)
    trigger_frequency: str | None = Field(default=None, pattern=AutomationFrequency)
    trigger_time: str | None = None
    timezone: str | None = None
    status: str | None = Field(default=None, pattern=AutomationStatus)
    config_json: dict | None = None
    workspace_id: str | None = None


class AutomationRead(TimestampedModel):
    user_id: str
    workspace_id: str | None = None
    name: str
    description: str | None = None
    automation_type: str
    assigned_agent: str
    trigger_frequency: str
    trigger_time: str | None = None
    timezone: str
    status: str
    config_json: dict
    last_run_at: datetime | None = None
    next_run_at: datetime | None = None
    updated_at: datetime


class AutomationRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    automation_id: str
    user_id: str
    workspace_id: str | None = None
    assigned_agent: str
    status: str
    started_at: datetime
    completed_at: datetime | None = None
    output_title: str | None = None
    output_summary: str | None = None
    output_content: str = ""
    error_message: str | None = None
    metadata_json: dict = Field(default_factory=dict)
