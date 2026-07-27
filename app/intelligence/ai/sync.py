from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from time import perf_counter
from typing import Any

from app.core.config.settings import settings
from app.intelligence.ai.errors import AIServiceUnavailableError

logger = logging.getLogger(__name__)


def generate_text_sync(*, instructions: str, input_text: str, temperature: float | None = None, max_output_tokens: int | None = None) -> str:
    from app.intelligence.ai.ai_provider_service import ai_provider_service

    async def _generate() -> str:
        last_error: Exception | None = None
        attempts = ai_provider_service.llm.candidates(max_count=max(1, settings.llm_max_fallbacks + 1))
        if not attempts:
            raise AIServiceUnavailableError("No LLM provider is configured.", retryable=False, category="configuration")
        for index, (provider_name, provider) in enumerate(attempts):
            started = perf_counter()
            try:
                text = await provider.generate(
                    instructions=instructions,
                    input_text=input_text,
                    temperature=temperature,
                    max_output_tokens=max_output_tokens,
                )
                ai_provider_service.llm.router.record_success(provider_name, total_ms=(perf_counter() - started) * 1000)
                logger.info("AI provider succeeded: provider=%s total_ms=%s", provider_name, round((perf_counter() - started) * 1000))
                return text
            except AIServiceUnavailableError as exc:
                last_error = exc
                ai_provider_service.llm.router.record_failure(provider_name, exc)
                logger.warning(
                    "AI provider failed: provider=%s retryable=%s category=%s detail=%s",
                    provider_name,
                    exc.retryable,
                    exc.category,
                    exc.detail,
                )
                if not exc.retryable or index >= len(attempts) - 1:
                    break
            except Exception as exc:  # noqa: BLE001
                last_error = AIServiceUnavailableError(repr(exc), retryable=True, provider=provider_name, category="unexpected")
                ai_provider_service.llm.router.record_failure(provider_name, last_error)
                logger.warning("AI provider failed unexpectedly: provider=%s error=%s", provider_name, repr(exc))
                if index >= len(attempts) - 1:
                    break
        raise AIServiceUnavailableError(repr(last_error), retryable=False)

    return asyncio.run(_generate())


async def stream_text(
    *,
    instructions: str,
    input_text: str,
    temperature: float | None = None,
    max_output_tokens: int | None = None,
    trace: dict[str, Any] | None = None,
) -> AsyncIterator[str]:
    from app.intelligence.ai.ai_provider_service import ai_provider_service

    last_error: Exception | None = None
    attempts = ai_provider_service.llm.candidates(max_count=max(1, settings.llm_max_fallbacks + 1))
    if not attempts:
        raise AIServiceUnavailableError("No LLM provider is configured.", retryable=False, category="configuration")

    for index, (provider_name, provider) in enumerate(attempts):
        started = perf_counter()
        first_token_ms: float | None = None
        try:
            if trace is not None:
                trace["provider"] = provider_name
                trace["model"] = getattr(provider, "default_model", None)
                trace["fallback"] = index > 0
                trace["provider_attempt"] = index + 1
            async for chunk in provider.stream(
                instructions=instructions,
                input_text=input_text,
                model=None,
            ):
                if not chunk:
                    continue
                if first_token_ms is None:
                    first_token_ms = (perf_counter() - started) * 1000
                    if trace is not None:
                        trace["first_token_ms"] = round(first_token_ms, 2)
                yield chunk
            total_ms = (perf_counter() - started) * 1000
            ai_provider_service.llm.router.record_success(
                provider_name,
                total_ms=total_ms,
                first_token_ms=first_token_ms,
            )
            logger.info(
                "AI provider stream succeeded: provider=%s first_token_ms=%s total_ms=%s",
                provider_name,
                None if first_token_ms is None else round(first_token_ms, 2),
                round(total_ms, 2),
            )
            return
        except AIServiceUnavailableError as exc:
            last_error = exc
            ai_provider_service.llm.router.record_failure(provider_name, exc)
            logger.warning(
                "AI provider stream failed: provider=%s retryable=%s category=%s detail=%s",
                provider_name,
                exc.retryable,
                exc.category,
                exc.detail,
            )
            if not exc.retryable or index >= len(attempts) - 1:
                break
        except Exception as exc:  # noqa: BLE001
            last_error = AIServiceUnavailableError(repr(exc), retryable=True, provider=provider_name, category="unexpected")
            ai_provider_service.llm.router.record_failure(provider_name, last_error)
            logger.warning("AI provider stream failed unexpectedly: provider=%s error=%s", provider_name, repr(exc))
            if index >= len(attempts) - 1:
                break

    raise AIServiceUnavailableError(repr(last_error), retryable=False)
