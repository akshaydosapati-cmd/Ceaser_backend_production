from __future__ import annotations

from collections.abc import Iterable

import httpx

from app.intelligence.ai.errors import AIServiceUnavailableError


RETRYABLE_STATUS_CODES = {408, 425, 429, 500, 502, 503, 504}
NON_RETRYABLE_STATUS_CODES = {400, 401, 403, 404, 422}


def ai_error_from_http_error(
    exc: httpx.HTTPStatusError | httpx.RequestError,
    *,
    provider: str,
    category: str = "generation",
) -> AIServiceUnavailableError:
    if isinstance(exc, httpx.RequestError):
        return AIServiceUnavailableError(
            f"{provider} network error: {exc.__class__.__name__}",
            retryable=True,
            provider=provider,
            category="network",
        )

    status_code = exc.response.status_code
    body = _truncate(_safe_response_text(exc.response))
    return ai_error_from_status(status_code=status_code, body=body, provider=provider, category=category)


def ai_error_from_status(
    *,
    status_code: int,
    body: str,
    provider: str,
    category: str = "generation",
) -> AIServiceUnavailableError:
    retryable = status_code in RETRYABLE_STATUS_CODES
    if status_code in NON_RETRYABLE_STATUS_CODES:
        retryable = False
    if _looks_like_policy_or_prompt_error(body):
        retryable = False
    detail = body or f"{provider} returned HTTP {status_code}"
    return AIServiceUnavailableError(detail, retryable=retryable, provider=provider, category=category)


def _truncate(value: str, max_length: int = 1200) -> str:
    return value[:max_length]


def _safe_response_text(response: httpx.Response) -> str:
    try:
        return response.text
    except httpx.ResponseNotRead:
        return ""


def _looks_like_policy_or_prompt_error(body: str) -> bool:
    normalized = body.lower()
    terms: Iterable[str] = (
        "safety",
        "policy",
        "refused",
        "invalid prompt",
        "malformed",
        "bad request",
    )
    return any(term in normalized for term in terms)
