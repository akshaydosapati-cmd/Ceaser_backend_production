from __future__ import annotations

import logging

import httpx

from app.core.config.settings import settings
from app.intelligence.ai.errors import AIServiceUnavailableError
from app.intelligence.ai.embeddings.base import EmbeddingProvider

logger = logging.getLogger(__name__)


class OpenAIEmbeddingProvider(EmbeddingProvider):
    endpoint = "https://api.openai.com/v1/embeddings"

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return await self._embed(texts)

    async def embed_query(self, query: str) -> list[float]:
        vectors = await self._embed([query])
        return vectors[0] if vectors else []

    async def _embed(self, texts: list[str]) -> list[list[float]]:
        if not settings.openai_api_key:
            logger.error("OpenAI embedding blocked: OPENAI_API_KEY is not configured.")
            raise AIServiceUnavailableError("OPENAI_API_KEY is not configured.")
        async with httpx.AsyncClient(timeout=45) as client:
            try:
                response = await client.post(
                    self.endpoint,
                    headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                    json={"model": settings.openai_embedding_model, "input": texts},
                )
                response.raise_for_status()
                data = response.json()
            except httpx.HTTPStatusError as exc:
                logger.error(
                    "OpenAI embedding failed: status=%s body=%s",
                    exc.response.status_code,
                    exc.response.text[:1200],
                )
                raise AIServiceUnavailableError(exc.response.text[:1200]) from exc
            except httpx.RequestError as exc:
                logger.error("OpenAI embedding network error: %s", repr(exc))
                raise AIServiceUnavailableError(repr(exc)) from exc
        return [item["embedding"] for item in sorted(data.get("data", []), key=lambda item: item.get("index", 0))]
