from __future__ import annotations

import asyncio
import logging

from app.intelligence.ai.errors import AIServiceUnavailableError

logger = logging.getLogger(__name__)


def generate_text_sync(*, instructions: str, input_text: str, temperature: float | None = None, max_output_tokens: int | None = None) -> str:
    from app.intelligence.ai.ai_provider_service import ai_provider_service

    async def _generate() -> str:
        last_error: Exception | None = None
        for name, provider in (
            ("production", ai_provider_service.llm.production()),
            ("fallback", ai_provider_service.llm.fallback()),
        ):
            try:
                return await provider.generate(
                    instructions=instructions,
                    input_text=input_text,
                    temperature=temperature,
                    max_output_tokens=max_output_tokens,
                )
            except Exception as exc:
                last_error = exc
                logger.error("AI %s provider failed; trying next provider if available: %s", name, repr(exc))
        raise AIServiceUnavailableError(repr(last_error))

    return asyncio.run(_generate())
