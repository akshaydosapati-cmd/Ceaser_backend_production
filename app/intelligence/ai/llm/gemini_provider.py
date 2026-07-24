from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.core.config.settings import settings
from app.intelligence.ai.errors import AIServiceUnavailableError
from app.intelligence.ai.llm.base import LLMProvider

logger = logging.getLogger(__name__)


class GeminiFallbackProvider(LLMProvider):
    async def generate(
        self,
        *,
        instructions: str,
        input_text: str,
        model: str | None = None,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> str:
        data = await self._post(
            prompt=f"{instructions}\n\n{input_text}",
            model=model or settings.gemini_model,
            temperature=temperature if temperature is not None else settings.gemini_temperature,
            max_tokens=max_output_tokens or settings.gemini_max_tokens,
        )
        return self._extract_text(data)

    async def generate_json(
        self,
        *,
        instructions: str,
        input_text: str,
        schema: dict[str, Any],
        model: str | None = None,
    ) -> dict[str, Any]:
        text = await self.generate(
            instructions=f"{instructions}\nReturn valid JSON only for this schema: {json.dumps(schema)}",
            input_text=input_text,
            model=model,
            temperature=0.2,
        )
        return json.loads(text)

    async def stream(
        self,
        *,
        instructions: str,
        input_text: str,
        model: str | None = None,
    ) -> AsyncIterator[str]:
        yield await self.generate(instructions=instructions, input_text=input_text, model=model)

    async def _post(self, *, prompt: str, model: str, temperature: float, max_tokens: int) -> dict[str, Any]:
        if not settings.gemini_api_key:
            logger.error("Gemini fallback blocked: GEMINI_API_KEY is not configured.")
            raise AIServiceUnavailableError("GEMINI_API_KEY is not configured.")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens},
        }
        try:
            async with httpx.AsyncClient(timeout=45) as client:
                response = await client.post(url, params={"key": settings.gemini_api_key}, json=payload)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as exc:
            logger.error(
                "Gemini fallback failed: status=%s body=%s",
                exc.response.status_code,
                exc.response.text[:1200],
            )
            raise AIServiceUnavailableError(exc.response.text[:1200]) from exc
        except httpx.RequestError as exc:
            logger.error("Gemini fallback network error: %s", repr(exc))
            raise AIServiceUnavailableError(repr(exc)) from exc

    def _extract_text(self, data: dict[str, Any]) -> str:
        candidates = data.get("candidates") or []
        if not candidates:
            return ""
        parts = candidates[0].get("content", {}).get("parts", [])
        return "\n".join(part.get("text", "") for part in parts if part.get("text")).strip()
