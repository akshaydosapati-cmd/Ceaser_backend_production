from __future__ import annotations

from app.intelligence.ai.embeddings.base import EmbeddingProvider
from app.intelligence.ai.embeddings.openai_embedding_provider import OpenAIEmbeddingProvider


class EmbeddingRegistry:
    def production(self) -> EmbeddingProvider:
        return OpenAIEmbeddingProvider()


embedding_registry = EmbeddingRegistry()

