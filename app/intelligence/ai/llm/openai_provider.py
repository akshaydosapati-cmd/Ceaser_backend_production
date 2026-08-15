from __future__ import annotations

import json
import logging
import re
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
    responses_endpoint = "https://api.openai.com/v1/responses"
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
        # Public-web evidence is collected by ResearchEngine (Serper) before
        # this provider is called. OpenAI's web tool would bypass that flow,
        # hide the source selection from CEASER, and spend a second search.
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
            # Streaming must either begin promptly or let the router try the
            # next provider. A 45-second initial read defeats failover.
            read=min(settings.llm_first_token_timeout_seconds, 4.0),
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
            logger.error("OpenAI stream failed: status=%s", exc.response.status_code)
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
            logger.error("OpenAI generation failed: status=%s", exc.response.status_code)
            raise ai_error_from_http_error(exc, provider="openai") from exc
        except httpx.RequestError as exc:
            logger.error("OpenAI generation network error: %s", repr(exc))
            raise ai_error_from_http_error(exc, provider="openai") from exc

    async def _responses_web_generate(
        self,
        *,
        instructions: str,
        input_text: str,
        max_output_tokens: int,
        trace: dict[str, Any] | None = None,
    ) -> str:
        if not settings.openai_web_search_enabled:
            raise AIServiceUnavailableError("OpenAI web search is disabled.", retryable=True, provider="openai", category="configuration")
        if not settings.openai_api_key:
            logger.error("OpenAI web search blocked: OPENAI_API_KEY is not configured.")
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
            "model": settings.openai_web_search_model,
            "instructions": instructions,
            "input": input_text,
            "tools": [{"type": "web_search_preview"}],
            "max_output_tokens": max_output_tokens,
        }
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                started = time.perf_counter()
                response = await client.post(
                    self.responses_endpoint,
                    headers={"Authorization": f"Bearer {settings.openai_api_key}", "Content-Type": "application/json"},
                    json=payload,
                )
                response.raise_for_status()
                if trace is not None:
                    trace["provider_connect_ms"] = round((time.perf_counter() - started) * 1000, 2)
                    trace["model"] = settings.openai_web_search_model
                    trace["web_search_used"] = True
                data = response.json()
                usage = data.get("usage") or {}
                logger.info(
                    "llm_usage provider=openai_web_search model=%s input_tokens=%s output_tokens=%s total_tokens=%s",
                    settings.openai_web_search_model,
                    usage.get("input_tokens"),
                    usage.get("output_tokens"),
                    usage.get("total_tokens"),
                )
                return self._extract_responses_text(data)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429 and "insufficient_quota" in exc.response.text:
                _quota_blocked_until = time.time() + 600
            logger.error("OpenAI web search failed: status=%s", exc.response.status_code)
            raise ai_error_from_http_error(exc, provider="openai") from exc
        except httpx.RequestError as exc:
            logger.error("OpenAI web search network error: %s", repr(exc))
            raise ai_error_from_http_error(exc, provider="openai") from exc

    def _extract_text(self, data: dict[str, Any]) -> str:
        choices = data.get("choices") or []
        if not choices:
            return ""
        content = choices[0].get("message", {}).get("content")
        return content.strip() if isinstance(content, str) else ""

    def _extract_responses_text(self, data: dict[str, Any]) -> str:
        output_text = data.get("output_text")
        if isinstance(output_text, str) and output_text.strip():
            return self._hide_visible_sources(output_text)
        parts: list[str] = []
        for item in data.get("output") or []:
            for content in item.get("content") or []:
                text = content.get("text") if isinstance(content, dict) else None
                if isinstance(text, str) and text:
                    parts.append(text)
        return self._hide_visible_sources("\n".join(parts))

    def _hide_visible_sources(self, text: str) -> str:
        cleaned = re.sub(r"\[\d+\]", "", text)
        cleaned = re.sub(r"\(\s*https?://[^)\s]+\s*\)", "", cleaned)
        cleaned = re.sub(r"https?://\S+", "", cleaned)
        cleaned = re.split(r"\n\s*(?:sources|references|citations)\s*:?\s*\n", cleaned, flags=re.IGNORECASE)[0]
        return re.sub(r"[ \t]+\n", "\n", cleaned).strip()

    def _requires_live_web(self, instructions: str, input_text: str) -> bool:
        if not settings.openai_web_search_enabled:
            return False
        text = f"{instructions}\n{input_text}".lower()
        return any(
            term in text
            for term in [
                "current stats",
                "latest stats",
                "current statistics",
                "latest statistics",
                "today",
                "latest",
                "current",
                "recent",
                "live data",
                "as of",
                "news",
                "stock price",
                "weather",
                "score",
                "who won",
                "centuries",
                "records",
            ]
        )

    def _progressive_chunks(self, text: str, *, maximum_length: int = 64) -> list[str]:
        words = text.split(" ")
        chunks: list[str] = []
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if current and len(candidate) > maximum_length:
                chunks.append(current + " ")
                current = word
            else:
                current = candidate
        if current:
            chunks.append(current)
        return chunks
