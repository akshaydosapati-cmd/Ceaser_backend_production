from __future__ import annotations

from app.services.llm.gemini_provider import GeminiProvider
from app.services.llm.provider import LLMProvider


class ResponsePipeline:
    def __init__(self, provider: LLMProvider | None = None):
        self.provider = provider or GeminiProvider()

    def generate(self, message: str, context: dict) -> str:
        return self.provider.generate_response(message=message, context=context)
