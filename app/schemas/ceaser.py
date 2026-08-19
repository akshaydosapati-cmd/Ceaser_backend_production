from __future__ import annotations

from pydantic import BaseModel, Field
from app.schemas.rich_response import CeaserRichResponse


class CeaserChatRequest(BaseModel):
    user_id: str | None = None
    message: str = Field(min_length=1)
    conversation_id: str | None = None
    request_id: str | None = None
    parent_message_id: str | None = None
    file_ids: list[str] = Field(default_factory=list)
    source: str | None = None
    voice: bool = False
    original_message: str | None = None
    device_id: str | None = Field(default=None, max_length=120)
    desktop_file_context: dict | None = None
    model_preference: str | None = None
    force_live_web_search: bool = False
    response_mode: str = "chat"
    image_model_preference: str | None = None


class RankedMemory(BaseModel):
    id: str
    user_id: str
    memory_type: str
    content: str
    metadata: dict = Field(default_factory=dict)
    created_at: str
    score: float


class AgentContributionResponse(BaseModel):
    agent: str
    domain: str
    analysis: str
    recommendations: list[str]
    frameworks_used: list[str]
    confidence: float


class ResearchSourceResponse(BaseModel):
    title: str
    url: str
    source: str
    snippet: str
    excerpt: str | None = None
    publisher: str | None = None
    retrieved_at: str | None = None
    image_url: str | None = None
    score: float = 0


class CitationResponse(BaseModel):
    title: str
    url: str


class ResearchImageResponse(BaseModel):
    title: str
    url: str
    image_url: str
    source: str


class ResearchResultResponse(BaseModel):
    query: str
    summary: str
    key_findings: list[str]
    sources: list[ResearchSourceResponse]
    citations: list[CitationResponse]
    images: list[ResearchImageResponse] = Field(default_factory=list)
    claims: list[dict] = Field(default_factory=list)
    statistics: list[dict] = Field(default_factory=list)
    comparisons: list[dict] = Field(default_factory=list)
    confidence: float | None = None
    unresolved_questions: list[str] = Field(default_factory=list)


class WorkflowResponse(BaseModel):
    id: str
    type: str
    status: str
    steps: list[dict]
    summary: str


class SuggestionResponse(BaseModel):
    text: str
    action_type: str
    category: str
    confidence: float
    label: str | None = None
    prompt: str | None = None
    conversation_id: str | None = None
    parent_message_id: str | None = None
    topic: str | None = None


class CeaserChatResponse(BaseModel):
    scope: str
    conversation_id: str | None = None
    selected_agents: list[str]
    contributions: list[AgentContributionResponse]
    contribution_summary: str
    memories_used: list[RankedMemory]
    research: ResearchResultResponse | None = None
    workflow: WorkflowResponse | None = None
    context_summary: dict
    suggestions: list[SuggestionResponse] = Field(default_factory=list)
    response: str
    rich_response: CeaserRichResponse | None = None
