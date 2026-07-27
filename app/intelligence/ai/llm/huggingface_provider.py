from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.core.config.settings import settings
from app.intelligence.ai.errors import AIServiceUnavailableError
from app.intelligence.ai.llm.base import LLMProvider
from app.intelligence.ai.llm.http_errors import ai_error_from_http_error

logger = logging.getLogger(__name__)


class HuggingFaceProvider(LLMProvider):
    base_url = "https://api-inference.huggingface.co/models"
    default_model = settings.huggingface_model

    async def generate(
        self,
        *,
        instructions: str,
        input_text: str,
        model: str | None = None,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> str:
        prompt = self._prompt(instructions=instructions, input_text=input_text)
        data = await self._post(
            prompt=prompt,
            model=model or settings.huggingface_model,
            temperature=temperature if temperature is not None else 0.2,
            max_new_tokens=max_output_tokens or settings.openai_max_tokens,
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
        trace: dict[str, Any] | None = None,
    ) -> AsyncIterator[str]:
        yield await self.generate(instructions=instructions, input_text=input_text, model=model)

    async def _post(self, *, prompt: str, model: str, temperature: float, max_new_tokens: int) -> Any:
        if not settings.huggingface_api_key:
            raise AIServiceUnavailableError(
                "HUGGINGFACE_API_KEY is not configured.",
                retryable=False,
                provider="huggingface",
                category="configuration",
            )
        url = f"{self.base_url}/{model}"
        payload = {
            "inputs": prompt,
            "parameters": {
                "temperature": temperature,
                "max_new_tokens": max_new_tokens,
                "return_full_text": False,
            },
        }
        try:
            timeout = httpx.Timeout(
                connect=settings.llm_connect_timeout_seconds,
                read=settings.llm_total_timeout_seconds,
                write=settings.llm_total_timeout_seconds,
                pool=settings.llm_total_timeout_seconds,
            )
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(url, headers={"Authorization": f"Bearer {settings.huggingface_api_key}"}, json=payload)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as exc:
            logger.error("Hugging Face generation failed: status=%s body=%s", exc.response.status_code, exc.response.text[:1200])
            raise ai_error_from_http_error(exc, provider="huggingface") from exc
        except httpx.RequestError as exc:
            logger.error("Hugging Face generation network error: %s", repr(exc))
            raise ai_error_from_http_error(exc, provider="huggingface") from exc

    def _extract_text(self, data: Any) -> str:
        if isinstance(data, list) and data:
            first = data[0]
            if isinstance(first, dict):
                text = first.get("generated_text") or first.get("summary_text") or ""
                return text.strip() if isinstance(text, str) else ""
        if isinstance(data, dict):
            text = data.get("generated_text") or data.get("summary_text") or ""
            if isinstance(text, str):
                return text.strip()
        return ""

    def _prompt(self, *, instructions: str, input_text: str) -> str:
        return (
            "You are CEASER, a serious personal AI operating system.\n"
            "Answer in clear, modern, useful English.\n"
            "Do not roleplay. Do not use Shakespearean, poetic, Latin, joke, or theatrical style unless the user asks for it.\n"
            "Give a complete, direct answer that fits the user's request.\n\n"
            f"Task instructions:\n{instructions}\n\n"
            f"User request and context:\n{input_text}"
        )
