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


class HuggingFaceProvider(LLMProvider):
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
        data = await self._post(
            model=model or settings.huggingface_model,
            instructions=instructions,
            input_text=input_text,
            temperature=temperature if temperature is not None else 0.2,
            max_tokens=max_output_tokens or settings.openai_max_tokens,
            stream=False,
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
            instructions=f"{instructions}\nReturn valid JSON only for this schema: {json.dumps(schema, ensure_ascii=True)}",
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
        max_output_tokens: int | None = None,
        trace: dict[str, Any] | None = None,
    ) -> AsyncIterator[str]:
        if trace is not None:
            trace["stream_opened"] = False
            trace["stream_completed"] = False
            trace["stream_cancelled"] = False
            trace["stream_error_type"] = None

        model_name = model or settings.huggingface_model
        endpoint = self._endpoint_url()
        hostname = urlparse(endpoint).hostname or "<invalid-host>"
        payload = self._payload(
            model=model_name,
            instructions=instructions,
            input_text=input_text,
            temperature=0.2,
            max_tokens=max_output_tokens or settings.openai_max_tokens,
            stream=True,
        )

        try:
            async with httpx.AsyncClient(timeout=self._timeout(streaming=True)) as client:
                connect_started = perf_counter()
                async with client.stream(
                    "POST",
                    endpoint,
                    headers=self._headers(),
                    json=payload,
                ) as response:
                    if response.status_code >= 400:
                        error_body = (await response.aread()).decode("utf-8", errors="replace")
                        raise self._status_error(
                            status_code=response.status_code,
                            body=error_body,
                            model=model_name,
                            endpoint=endpoint,
                        )
                    if trace is not None:
                        trace["stream_opened"] = True
                        trace["provider_connect_ms"] = round((perf_counter() - connect_started) * 1000, 2)

                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        if line.startswith("data: "):
                            data = line[6:].strip()
                        else:
                            continue
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                        except json.JSONDecodeError:
                            continue
                        if trace is not None:
                            reason = ((chunk.get("choices") or [{}])[0]).get("finish_reason")
                            if reason:
                                trace["finish_reason"] = str(reason)
                        delta = ((chunk.get("choices") or [{}])[0].get("delta") or {}).get("content")
                        if isinstance(delta, str) and delta:
                            yield delta
                    if trace is not None:
                        trace["stream_completed"] = True
        except (asyncio.CancelledError, GeneratorExit):
            if trace is not None:
                trace["stream_cancelled"] = True
                trace["stream_error_type"] = "cancelled"
            logger.warning("Hugging Face stream cancelled.")
            raise
        except AIServiceUnavailableError as exc:
            if trace is not None:
                trace["stream_error_type"] = exc.category or exc.__class__.__name__
            raise
        except httpx.TimeoutException as exc:
            if trace is not None:
                trace["stream_error_type"] = "timeout"
            logger.error("Hugging Face stream timeout: host=%s error=%s", hostname, repr(exc))
            raise AIServiceUnavailableError(
                f"huggingface timeout host={hostname}",
                retryable=True,
                provider="huggingface",
                category="timeout",
            ) from exc
        except httpx.RequestError as exc:
            if trace is not None:
                trace["stream_error_type"] = exc.__class__.__name__
            logger.error("Hugging Face stream network error: host=%s error=%s", hostname, repr(exc))
            raise self._request_error(exc=exc, hostname=hostname) from exc

    async def _post(
        self,
        *,
        model: str,
        instructions: str,
        input_text: str,
        temperature: float,
        max_tokens: int,
        stream: bool,
    ) -> dict[str, Any]:
        endpoint = self._endpoint_url()
        hostname = urlparse(endpoint).hostname or "<invalid-host>"
        try:
            async with httpx.AsyncClient(timeout=self._timeout(streaming=False)) as client:
                response = await client.post(
                    endpoint,
                    headers=self._headers(),
                    json=self._payload(
                        model=model,
                        instructions=instructions,
                        input_text=input_text,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        stream=stream,
                    ),
                )
                if response.status_code >= 400:
                    raise self._status_error(
                        status_code=response.status_code,
                        body=response.text,
                        model=model,
                        endpoint=endpoint,
                    )
                return response.json()
        except AIServiceUnavailableError:
            raise
        except httpx.TimeoutException as exc:
            logger.error("Hugging Face generation timeout: host=%s error=%s", hostname, repr(exc))
            raise AIServiceUnavailableError(
                f"huggingface timeout host={hostname}",
                retryable=True,
                provider="huggingface",
                category="timeout",
            ) from exc
        except httpx.RequestError as exc:
            logger.error("Hugging Face generation network error: host=%s error=%s", hostname, repr(exc))
            raise self._request_error(exc=exc, hostname=hostname) from exc

    def _payload(
        self,
        *,
        model: str,
        instructions: str,
        input_text: str,
        temperature: float,
        max_tokens: int,
        stream: bool,
    ) -> dict[str, Any]:
        return {
            "model": model,
            "messages": [
                {"role": "system", "content": instructions},
                {"role": "user", "content": input_text},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
        }

    def _headers(self) -> dict[str, str]:
        if not settings.huggingface_api_key:
            raise AIServiceUnavailableError(
                "HUGGINGFACE_API_KEY is not configured.",
                retryable=False,
                provider="huggingface",
                category="configuration",
            )
        return {
            "Authorization": f"Bearer {settings.huggingface_api_key}",
            "Content-Type": "application/json",
        }

    def _endpoint_url(self) -> str:
        return settings.huggingface_base_url.rstrip("/")

    def _timeout(self, *, streaming: bool) -> httpx.Timeout:
        return httpx.Timeout(
            connect=settings.llm_connect_timeout_seconds,
            read=min(settings.llm_first_token_timeout_seconds, 4.0) if streaming else settings.llm_total_timeout_seconds,
            write=settings.llm_total_timeout_seconds,
            pool=settings.llm_total_timeout_seconds,
        )

    def _status_error(
        self,
        *,
        status_code: int,
        body: str,
        model: str,
        endpoint: str,
    ) -> AIServiceUnavailableError:
        sanitized_body = (body or "").strip()[:1200]
        lowered = sanitized_body.lower()
        parsed = urlparse(endpoint)
        hostname = parsed.hostname or "<invalid-host>"
        logger.error(
            "Hugging Face request failed: status=%s host=%s model=%s body=%s",
            status_code,
            hostname,
            model,
            sanitized_body,
        )
        if status_code in {401, 403}:
            return AIServiceUnavailableError(
                f"huggingface authentication failed host={hostname}",
                retryable=False,
                provider="huggingface",
                category="authentication",
            )
        if status_code == 404 or "model" in lowered and (
            "not found" in lowered
            or "does not exist" in lowered
            or "not supported" in lowered
            or "model_not_supported" in lowered
        ):
            return AIServiceUnavailableError(
                f"huggingface model unavailable model={model}",
                retryable=True,
                provider="huggingface",
                category="model_unavailable",
            )
        if status_code == 429:
            return AIServiceUnavailableError(
                f"huggingface rate limited host={hostname}",
                retryable=True,
                provider="huggingface",
                category="rate_limit",
            )
        return ai_error_from_status(
            status_code=status_code,
            body=f"huggingface provider error status={status_code} host={hostname}",
            provider="huggingface",
            category="provider_error",
        )

    def _request_error(self, *, exc: httpx.RequestError, hostname: str) -> AIServiceUnavailableError:
        if isinstance(exc, httpx.ConnectError):
            return AIServiceUnavailableError(
                f"huggingface dns/connect failure host={hostname}",
                retryable=True,
                provider="huggingface",
                category="dns",
            )
        return AIServiceUnavailableError(
            f"huggingface network error: {exc.__class__.__name__} host={hostname}",
            retryable=True,
            provider="huggingface",
            category="network",
        )

    def _extract_text(self, data: Any) -> str:
        if isinstance(data, dict):
            choices = data.get("choices") or []
            if choices:
                content = choices[0].get("message", {}).get("content")
                if isinstance(content, str):
                    return content.strip()
        return ""
