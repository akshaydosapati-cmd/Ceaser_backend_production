from __future__ import annotations

import json
import logging
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.core.config.settings import settings
from app.intelligence.ai.errors import AIServiceUnavailableError
from app.intelligence.ai.llm.base import LLMProvider

logger = logging.getLogger(__name__)
_quota_blocked_until = 0.0


class OpenAIProvider(LLMProvider):
    endpoint = "https://api.openai.com/v1/chat/completions"

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
            model=model or settings.openai_model,
            instructions=instructions,
            input_text=input_text,
            temperature=temperature if temperature is not None else settings.openai_temperature,
            max_tokens=max_output_tokens or settings.openai_max_tokens,
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
        schema_instruction = (
            f"{instructions}\n\nReturn valid JSON only. The JSON must match this schema intent:\n"
            f"{json.dumps(schema, ensure_ascii=True)}"
        )
        data = await self._post(
            model=model or settings.openai_json_model,
            instructions=schema_instruction,
            input_text=input_text,
            temperature=0.2,
            max_tokens=settings.openai_max_tokens,
            response_format={"type": "json_object"},
        )
        text = self._extract_text(data)
        return json.loads(text)

    async def stream(
        self,
        *,
        instructions: str,
        input_text: str,
        model: str | None = None,
    ) -> AsyncIterator[str]:
        yield await self.generate(instructions=instructions, input_text=input_text, model=model)

    async def _post(
        self,
        *,
        model: str,
        instructions: str,
        input_text: str,
        temperature: float,
        max_tokens: int,
        response_format: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not settings.openai_api_key:
            logger.error("OpenAI request blocked: OPENAI_API_KEY is not configured.")
            raise AIServiceUnavailableError("OPENAI_API_KEY is not configured.")
        global _quota_blocked_until
        if time.time() < _quota_blocked_until:
            raise AIServiceUnavailableError("OpenAI quota circuit is temporarily open.")
        payload: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": instructions},
                {"role": "user", "content": input_text},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format:
            payload["response_format"] = response_format
        try:
            async with httpx.AsyncClient(timeout=settings.openai_request_timeout_seconds) as client:
                response = await client.post(
                    self.endpoint,
                    headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                    json=payload,
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429 and "insufficient_quota" in exc.response.text:
                _quota_blocked_until = time.time() + 600
            logger.error(
                "OpenAI generation failed: status=%s body=%s",
                exc.response.status_code,
                exc.response.text[:1200],
            )
            raise AIServiceUnavailableError(exc.response.text[:1200]) from exc
        except httpx.RequestError as exc:
            logger.error("OpenAI generation network error: %s", repr(exc))
            raise AIServiceUnavailableError(repr(exc)) from exc

    def _extract_text(self, data: dict[str, Any]) -> str:
        choices = data.get("choices") or []
        if not choices:
            return ""
        content = choices[0].get("message", {}).get("content")
        return content.strip() if isinstance(content, str) else ""
