from __future__ import annotations

from pydantic import BaseModel, Field


class CeaserChatRequest(BaseModel):
    user_id: str | None = None
    message: str = Field(min_length=1)
    conversation_id: str | None = None
    request_id: str | None = None
    parent_message_id: str | None = None
    file_ids: list[str] = Field(default_factory=list)


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
    score: float = 0


class CitationResponse(BaseModel):
    title: str
    url: str


class ResearchResultResponse(BaseModel):
    query: str
    summary: str
    key_findings: list[str]
    sources: list[ResearchSourceResponse]
    citations: list[CitationResponse]


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
