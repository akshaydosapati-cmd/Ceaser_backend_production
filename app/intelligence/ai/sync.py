from __future__ import annotations

import asyncio


def generate_text_sync(*, instructions: str, input_text: str, temperature: float | None = None, max_output_tokens: int | None = None) -> str:
    from app.intelligence.ai.ai_provider_service import ai_provider_service

    provider = ai_provider_service.llm.production()
    return asyncio.run(
        provider.generate(
            instructions=instructions,
            input_text=input_text,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
        )
    )
