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
from app.intelligence.ai.llm.http_errors import ai_error_from_http_error

logger = logging.getLogger(__name__)
_quota_blocked_until = 0.0


class OpenAIProvider(LLMProvider):
    endpoint = "https://api.openai.com/v1/chat/completions"
    default_model = settings.openai_model

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
        max_output_tokens: int | None = None,
        trace: dict[str, Any] | None = None,
    ) -> AsyncIterator[str]:
        if not settings.openai_api_key:
            logger.error("OpenAI stream blocked: OPENAI_API_KEY is not configured.")
            raise AIServiceUnavailableError("OPENAI_API_KEY is not configured.")
        global _quota_blocked_until
        if time.time() < _quota_blocked_until:
            raise AIServiceUnavailableError("OpenAI quota circuit is temporarily open.")
        timeout = httpx.Timeout(
            connect=settings.llm_connect_timeout_seconds,
            read=settings.llm_total_timeout_seconds,
            write=settings.llm_total_timeout_seconds,
            pool=settings.llm_total_timeout_seconds,
        )
        payload: dict[str, Any] = {
            "model": model or settings.openai_model,
            "messages": [
                {"role": "system", "content": instructions},
                {"role": "user", "content": input_text},
            ],
            "temperature": settings.openai_temperature,
            "max_tokens": max_output_tokens or settings.openai_max_tokens,
            "stream": True,
        }
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                connect_started = time.perf_counter()
                async with client.stream(
                    "POST",
                    self.endpoint,
                    headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                    json=payload,
                ) as response:
                    response.raise_for_status()
                    if trace is not None:
                        trace["provider_connect_ms"] = round((time.perf_counter() - connect_started) * 1000, 2)
                        if "request_id" in trace:
                            logger.info(
                                "ceaser_stream_stage request_id=%s stage=provider_connected provider=openai model=%s provider_connect_ms=%s",
                                trace["request_id"],
                                model or settings.openai_model,
                                trace["provider_connect_ms"],
                            )
                    async for line in response.aiter_lines():
                        if not line or not line.startswith("data: "):
                            continue
                        data = line[6:].strip()
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                        except json.JSONDecodeError:
                            continue
                        delta = ((chunk.get("choices") or [{}])[0].get("delta") or {}).get("content")
                        if isinstance(delta, str) and delta:
                            yield delta
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429 and "insufficient_quota" in exc.response.text:
                _quota_blocked_until = time.time() + 600
            logger.error(
                "OpenAI stream failed: status=%s body=%s",
                exc.response.status_code,
                exc.response.text[:1200],
            )
            raise ai_error_from_http_error(exc, provider="openai") from exc
        except httpx.RequestError as exc:
            logger.error("OpenAI stream network error: %s", repr(exc))
            raise ai_error_from_http_error(exc, provider="openai") from exc

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
        timeout = httpx.Timeout(
            connect=settings.llm_connect_timeout_seconds,
            read=settings.llm_total_timeout_seconds,
            write=settings.llm_total_timeout_seconds,
            pool=settings.llm_total_timeout_seconds,
        )
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
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    self.endpoint,
                    headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
                usage = data.get("usage") or {}
                logger.info(
                    "llm_usage provider=openai model=%s prompt_tokens=%s completion_tokens=%s total_tokens=%s",
                    model,
                    usage.get("prompt_tokens"),
                    usage.get("completion_tokens"),
                    usage.get("total_tokens"),
                )
                return data
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429 and "insufficient_quota" in exc.response.text:
                _quota_blocked_until = time.time() + 600
            logger.error(
                "OpenAI generation failed: status=%s body=%s",
                exc.response.status_code,
                exc.response.text[:1200],
            )
            raise ai_error_from_http_error(exc, provider="openai") from exc
        except httpx.RequestError as exc:
            logger.error("OpenAI generation network error: %s", repr(exc))
            raise ai_error_from_http_error(exc, provider="openai") from exc

    def _extract_text(self, data: dict[str, Any]) -> str:
        choices = data.get("choices") or []
        if not choices:
            return ""
        content = choices[0].get("message", {}).get("content")
        return content.strip() if isinstance(content, str) else ""
