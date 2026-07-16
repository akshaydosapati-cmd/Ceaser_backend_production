from __future__ import annotations

from app.intelligence.ai.embeddings.registry import embedding_registry
from app.intelligence.ai.llm.registry import llm_registry


class AIProviderService:
    llm = llm_registry
    embeddings = embedding_registry


ai_provider_service = AIProviderService()

