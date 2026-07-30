from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from time import perf_counter
from typing import Any

import httpx

from app.core.config.settings import settings
from app.intelligence.ai.errors import AIServiceUnavailableError
from app.intelligence.ai.llm.base import LLMProvider
from app.intelligence.ai.llm.http_errors import ai_error_from_http_error, ai_error_from_status

logger = logging.getLogger(__name__)


class GroqProvider(LLMProvider):
    endpoint = "https://api.groq.com/openai/v1/chat/completions"
    default_model = settings.groq_model

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
            model=model or settings.groq_model,
            instructions=instructions,
            input_text=input_text,
            temperature=temperature if temperature is not None else 0.3,
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
            model=model or settings.groq_model,
            instructions=schema_instruction,
            input_text=input_text,
            temperature=0.2,
            max_tokens=settings.openai_max_tokens,
            response_format={"type": "json_object"},
        )
        return json.loads(self._extract_text(data))

    async def stream(
        self,
        *,
        instructions: str,
        input_text: str,
        model: str | None = None,
        max_output_tokens: int | None = None,
        trace: dict[str, Any] | None = None,
    ) -> AsyncIterator[str]:
        if not settings.groq_api_key:
            raise AIServiceUnavailableError("GROQ_API_KEY is not configured.", retryable=False, provider="groq", category="configuration")
        payload: dict[str, Any] = {
            "model": model or settings.groq_model,
            "messages": [
                {"role": "system", "content": instructions},
                {"role": "user", "content": input_text},
            ],
            "temperature": 0.3,
            "max_tokens": max_output_tokens or settings.openai_max_tokens,
            "stream": True,
        }
        try:
            timeout = httpx.Timeout(
                connect=settings.llm_connect_timeout_seconds,
            read=min(settings.llm_first_token_timeout_seconds, 4.0),
                write=settings.llm_total_timeout_seconds,
                pool=settings.llm_total_timeout_seconds,
            )
            async with httpx.AsyncClient(timeout=timeout) as client:
                connect_started = perf_counter()
                if trace is not None:
                    trace["stream_opened"] = False
                    trace["stream_completed"] = False
                    trace["stream_cancelled"] = False
                    trace["stream_error_type"] = None
                async with client.stream(
                    "POST",
                    self.endpoint,
                    headers={"Authorization": f"Bearer {settings.groq_api_key}"},
                    json=payload,
                ) as response:
                    if response.status_code >= 400:
                        error_body = (await response.aread()).decode("utf-8", errors="replace")
                        logger.error("Groq stream failed: status=%s body=%s", response.status_code, error_body[:1200])
                        raise ai_error_from_status(
                            status_code=response.status_code,
                            body=error_body[:1200],
                            provider="groq",
                        )
                    if trace is not None:
                        trace["stream_opened"] = True
                        trace["provider_connect_ms"] = round((perf_counter() - connect_started) * 1000, 2)
                        if "request_id" in trace:
                            logger.info(
                                "ceaser_stream_stage request_id=%s stage=provider_connected provider=groq model=%s provider_connect_ms=%s",
                                trace["request_id"],
                                model or settings.groq_model,
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
                    if trace is not None:
                        trace["stream_completed"] = True
        except (asyncio.CancelledError, GeneratorExit):
            if trace is not None:
                trace["stream_cancelled"] = True
                trace["stream_error_type"] = "cancelled"
            logger.warning("Groq stream cancelled.")
            raise
        except AIServiceUnavailableError as exc:
            if trace is not None:
                trace["stream_error_type"] = exc.category or exc.__class__.__name__
            raise
        except httpx.HTTPStatusError as exc:
            logger.error("Groq stream failed: status=%s", exc.response.status_code)
            if trace is not None:
                trace["stream_error_type"] = "http_status"
            raise ai_error_from_http_error(exc, provider="groq") from exc
        except httpx.TimeoutException as exc:
            logger.error("Groq stream timeout error: %s", repr(exc))
            if trace is not None:
                trace["stream_error_type"] = "timeout"
            raise ai_error_from_http_error(exc, provider="groq") from exc
        except httpx.RequestError as exc:
            logger.error("Groq stream network error: %s", repr(exc))
            if trace is not None:
                trace["stream_error_type"] = exc.__class__.__name__
            raise ai_error_from_http_error(exc, provider="groq") from exc

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
        if not settings.groq_api_key:
            raise AIServiceUnavailableError("GROQ_API_KEY is not configured.", retryable=False, provider="groq", category="configuration")
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
            timeout = httpx.Timeout(
                connect=settings.llm_connect_timeout_seconds,
                read=settings.llm_total_timeout_seconds,
                write=settings.llm_total_timeout_seconds,
                pool=settings.llm_total_timeout_seconds,
            )
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    self.endpoint,
                    headers={"Authorization": f"Bearer {settings.groq_api_key}"},
                    json=payload,
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as exc:
            logger.error("Groq generation failed: status=%s body=%s", exc.response.status_code, exc.response.text[:1200])
            raise ai_error_from_http_error(exc, provider="groq") from exc
        except httpx.RequestError as exc:
            logger.error("Groq generation network error: %s", repr(exc))
            raise ai_error_from_http_error(exc, provider="groq") from exc

    def _extract_text(self, data: dict[str, Any]) -> str:
        choices = data.get("choices") or []
        if not choices:
            return ""
        content = choices[0].get("message", {}).get("content")
        return content.strip() if isinstance(content, str) else ""
