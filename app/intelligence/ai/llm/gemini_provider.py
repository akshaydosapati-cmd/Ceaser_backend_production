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
        prompt = self._prompt(instructions=instructions, input_text=input_text)
        data = await self._post(
            prompt=prompt,
            model=model or settings.gemini_model,
            temperature=temperature if temperature is not None else settings.gemini_temperature,
            max_tokens=max_output_tokens or settings.gemini_max_tokens,
        )
        text = self._extract_text(data)
        if self._needs_retry(text):
            data = await self._post(
                prompt=self._retry_prompt(instructions=instructions, input_text=input_text, bad_answer=text),
                model=model or settings.gemini_model,
                temperature=0.2,
                max_tokens=max(max_output_tokens or settings.gemini_max_tokens, 900),
            )
            text = self._extract_text(data)
        return text

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
            timeout = httpx.Timeout(
                connect=settings.llm_connect_timeout_seconds,
                read=settings.llm_total_timeout_seconds,
                write=settings.llm_total_timeout_seconds,
                pool=settings.llm_total_timeout_seconds,
            )
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(url, params={"key": settings.gemini_api_key}, json=payload)
                response.raise_for_status()
                logger.info("Gemini fallback generation succeeded.")
                data = response.json()
                usage = data.get("usageMetadata") or {}
                logger.info(
                    "llm_usage provider=gemini model=%s prompt_tokens=%s completion_tokens=%s total_tokens=%s",
                    model,
                    usage.get("promptTokenCount"),
                    usage.get("candidatesTokenCount"),
                    usage.get("totalTokenCount"),
                )
                return data
        except httpx.HTTPStatusError as exc:
            logger.error(
                "Gemini fallback failed: status=%s body=%s",
                exc.response.status_code,
                exc.response.text[:1200],
            )
            raise ai_error_from_http_error(exc, provider="gemini") from exc
        except httpx.RequestError as exc:
            logger.error("Gemini fallback network error: %s", repr(exc))
            raise ai_error_from_http_error(exc, provider="gemini") from exc

    def _extract_text(self, data: dict[str, Any]) -> str:
        candidates = data.get("candidates") or []
        if not candidates:
            return ""
        parts = candidates[0].get("content", {}).get("parts", [])
        return "\n".join(part.get("text", "") for part in parts if part.get("text")).strip()

    def _prompt(self, *, instructions: str, input_text: str) -> str:
        return (
            "You are CEASER, a serious personal AI operating system.\n"
            "Answer in clear, modern, useful English.\n"
            "Do not roleplay. Do not use Shakespearean, poetic, Latin, joke, or theatrical style unless the user asks for it.\n"
            "Give a complete, direct answer that fits the user's request.\n\n"
            f"Task instructions:\n{instructions}\n\n"
            f"User request and context:\n{input_text}"
        )

    def _retry_prompt(self, *, instructions: str, input_text: str, bad_answer: str) -> str:
        return (
            "Your previous answer was not acceptable because it was incomplete or used the wrong style.\n"
            "Rewrite it as CEASER: direct, practical, complete, and student-friendly.\n"
            "No roleplay. No archaic language. No Latin. No jokes.\n\n"
            f"Task instructions:\n{instructions}\n\n"
            f"User request and context:\n{input_text}\n\n"
            f"Bad answer to replace:\n{bad_answer}"
        )

    def _needs_retry(self, text: str) -> bool:
        normalized = text.strip().lower()
        if len(normalized) < 80:
            return True
        blocked_starts = ("hark", "verily", "thou", "veni", "behold", "young scholar")
        return normalized.startswith(blocked_starts)
