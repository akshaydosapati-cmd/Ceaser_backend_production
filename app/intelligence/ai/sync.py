from __future__ import annotations

import asyncio

from app.intelligence.ai.llm.registry import llm_registry


def generate_text_sync(*, instructions: str, input_text: str, temperature: float | None = None, max_output_tokens: int | None = None) -> str:
    provider = llm_registry.production()
    return asyncio.run(
        provider.generate(
            instructions=instructions,
            input_text=input_text,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
        )
    )

