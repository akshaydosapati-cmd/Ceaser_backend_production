from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from time import perf_counter
from typing import Any
from urllib.parse import urlparse

import httpx

from app.core.config.settings import settings
from app.intelligence.ai.errors import AIServiceUnavailableError
from app.intelligence.ai.llm.base import LLMProvider
from app.intelligence.ai.llm.http_errors import ai_error_from_status


logger = logging.getLogger(__name__)


class NvidiaProvider(LLMProvider):
    """NVIDIA hosted NIM adapter using its OpenAI-compatible chat API."""

    default_model = settings.nvidia_model

    async def generate(
        self, *, instructions: str, input_text: str, model: str | None = None,
        temperature: float | None = None, max_output_tokens: int | None = None,
    ) -> str:
        data = await self._post(
            model=model or settings.nvidia_model, instructions=instructions, input_text=input_text,
            temperature=temperature if temperature is not None else 0.3,
            max_tokens=max_output_tokens or settings.openai_max_tokens,
        )
        return self._extract_text(data)

    async def generate_json(
        self, *, instructions: str, input_text: str, schema: dict[str, Any], model: str | None = None,
    ) -> dict[str, Any]:
        text = await self.generate(
            instructions=f"{instructions}\nReturn valid JSON only matching this schema intent: {json.dumps(schema, ensure_ascii=True)}",
            input_text=input_text, model=model, temperature=0.2,
        )
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise AIServiceUnavailableError(
                "NVIDIA returned invalid structured output.", retryable=True,
                provider="nvidia", category="invalid_response",
            ) from exc

    async def stream(
        self, *, instructions: str, input_text: str, model: str | None = None,
        max_output_tokens: int | None = None, trace: dict[str, Any] | None = None,
    ) -> AsyncIterator[str]:
        model_name = model or settings.nvidia_model
        if trace is not None:
            trace.update(stream_opened=False, stream_completed=False, stream_cancelled=False, stream_error_type=None)
        try:
            async with httpx.AsyncClient(timeout=self._stream_timeout()) as client:
                started = perf_counter()
                async with client.stream(
                    "POST", self._endpoint(), headers=self._headers(),
                    json=self._payload(model_name, instructions, input_text, max_output_tokens or settings.openai_max_tokens, True),
                ) as response:
                    if response.status_code >= 400:
                        body = (await response.aread()).decode("utf-8", errors="replace")
                        raise self._status_error(response.status_code, body, model_name)
                    if trace is not None:
                        trace["stream_opened"] = True
                        trace["provider_connect_ms"] = round((perf_counter() - started) * 1000, 2)
                    emitted_content = False
                    finish_reason: str | None = None
                    non_sse_lines: list[str] = []
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            if line.strip():
                                non_sse_lines.append(line)
                            continue
                        raw = line[5:].strip()
                        if raw == "[DONE]":
                            break
                        try:
                            chunk = json.loads(raw)
                        except json.JSONDecodeError:
                            continue
                        choice = (chunk.get("choices") or [{}])[0]
                        if choice.get("finish_reason"):
                            finish_reason = str(choice["finish_reason"])
                        delta = (choice.get("delta") or {}).get("content")
                        if isinstance(delta, str) and delta:
                            emitted_content = True
                            yield delta
                        elif isinstance(choice.get("message"), dict):
                            text = self._extract_text(chunk)
                            if text:
                                emitted_content = True
                                yield text
                    if not emitted_content and non_sse_lines:
                        try:
                            text = self._extract_text(json.loads("\n".join(non_sse_lines)))
                        except (json.JSONDecodeError, AIServiceUnavailableError):
                            text = ""
                        if text:
                            emitted_content = True
                            yield text
                    if not emitted_content:
                        raise AIServiceUnavailableError(
                            "NVIDIA stream contained no answer text.", retryable=True,
                            provider="nvidia", category="invalid_response",
                        )
                    if trace is not None:
                        trace["finish_reason"] = finish_reason
                        trace["stream_completed"] = True
        except (asyncio.CancelledError, GeneratorExit):
            if trace is not None:
                trace.update(stream_cancelled=True, stream_error_type="cancelled")
            raise
        except AIServiceUnavailableError as exc:
            if trace is not None:
                trace["stream_error_type"] = exc.category
            raise
        except httpx.TimeoutException as exc:
            if trace is not None:
                trace["stream_error_type"] = "timeout"
            raise self._request_error(exc) from exc
        except httpx.RequestError as exc:
            if trace is not None:
                trace["stream_error_type"] = "network_error"
            raise self._request_error(exc) from exc

    async def _post(self, *, model: str, instructions: str, input_text: str, temperature: float, max_tokens: int) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=self._timeout()) as client:
                response = await client.post(
                    self._endpoint(), headers=self._headers(),
                    json=self._payload(model, instructions, input_text, max_tokens, False, temperature),
                )
                if response.status_code >= 400:
                    raise self._status_error(response.status_code, response.text, model)
                return response.json()
        except AIServiceUnavailableError:
            raise
        except httpx.TimeoutException as exc:
            raise self._request_error(exc) from exc
        except httpx.RequestError as exc:
            raise self._request_error(exc) from exc
        except (ValueError, json.JSONDecodeError) as exc:
            raise AIServiceUnavailableError(
                "NVIDIA returned an invalid response.", retryable=True,
                provider="nvidia", category="invalid_response",
            ) from exc

    @staticmethod
    def _payload(model: str, instructions: str, input_text: str, max_tokens: int, stream: bool, temperature: float = 0.3) -> dict[str, Any]:
        return {
            "model": model,
            "messages": [{"role": "system", "content": instructions}, {"role": "user", "content": input_text}],
            "temperature": temperature, "max_tokens": max_tokens, "stream": stream,
            "chat_template_kwargs": {
                "force_nonempty_content": True,
                "enable_thinking": settings.nvidia_enable_thinking,
            },
        }

    def _headers(self) -> dict[str, str]:
        if not settings.nvidia_api_key:
            raise AIServiceUnavailableError(
                "NVIDIA_API_KEY is not configured.", retryable=False,
                provider="nvidia", category="configuration",
            )
        return {"Authorization": f"Bearer {settings.nvidia_api_key}", "Content-Type": "application/json"}

    @staticmethod
    def _endpoint() -> str:
        return f"{settings.nvidia_base_url.rstrip('/')}/chat/completions"

    @staticmethod
    def _timeout() -> httpx.Timeout:
        return httpx.Timeout(
            connect=settings.llm_connect_timeout_seconds, read=settings.nvidia_timeout_seconds,
            write=settings.nvidia_timeout_seconds, pool=settings.nvidia_timeout_seconds,
        )

    @staticmethod
    def _stream_timeout() -> httpx.Timeout:
        return httpx.Timeout(
            connect=settings.llm_connect_timeout_seconds,
            read=min(settings.nvidia_timeout_seconds, max(settings.llm_first_token_timeout_seconds, 30.0)),
            write=settings.nvidia_timeout_seconds, pool=settings.nvidia_timeout_seconds,
        )

    def _status_error(self, status: int, body: str, model: str) -> AIServiceUnavailableError:
        host = urlparse(self._endpoint()).hostname or "<invalid-host>"
        logger.warning("NVIDIA request failed: status=%s host=%s model=%s", status, host, model)
        if status in {401, 403}:
            return AIServiceUnavailableError(
                f"nvidia authentication failed host={host}", retryable=False,
                provider="nvidia", category="authentication",
            )
        if status == 429:
            return AIServiceUnavailableError(
                f"nvidia rate limited host={host}", retryable=True,
                provider="nvidia", category="rate_limit",
            )
        if status == 404:
            return AIServiceUnavailableError(
                f"nvidia model unavailable model={model}", retryable=False,
                provider="nvidia", category="model_unavailable",
            )
        return ai_error_from_status(
            status_code=status, body=f"nvidia provider error status={status} host={host}",
            provider="nvidia", category="provider_error",
        )

    @staticmethod
    def _request_error(exc: httpx.RequestError) -> AIServiceUnavailableError:
        category = "timeout" if isinstance(exc, httpx.TimeoutException) else "network_error"
        return AIServiceUnavailableError(
            f"nvidia {category}: {exc.__class__.__name__}", retryable=True,
            provider="nvidia", category=category,
        )

    @staticmethod
    def _extract_text(data: dict[str, Any]) -> str:
        choices = data.get("choices") or []
        content = (choices[0].get("message") or {}).get("content") if choices else None
        if not isinstance(content, str):
            raise AIServiceUnavailableError(
                "NVIDIA response contained no text.", retryable=True,
                provider="nvidia", category="invalid_response",
            )
        return content.strip()
