from __future__ import annotations

import asyncio
import json
import socket
import uuid
from collections.abc import AsyncIterator
from dataclasses import asdict
from dataclasses import dataclass
from time import perf_counter
from types import SimpleNamespace
from urllib.parse import urlparse

import httpx

from app.api.ceaser import routes as ceaser_routes
from app.core.config.settings import settings
from app.intelligence.ai.ai_provider_service import ai_provider_service
from app.intelligence.ai.errors import AIServiceUnavailableError
from app.intelligence.ai.llm.groq_provider import GroqProvider
from app.intelligence.ai.sync import stream_text
from app.main import app


PROMPT = "Explain Retrieval-Augmented Generation in exactly three clear paragraphs and give one practical CEASER example."


@dataclass
class RunResult:
    name: str
    status: str
    provider: str | None
    model: str | None
    first_token_ms: float | None
    total_ms: float | None
    words: int
    details: dict
    response: str


async def _collect_stream(async_iter: AsyncIterator[str]) -> tuple[str, float | None, float]:
    chunks: list[str] = []
    started = perf_counter()
    first_token_ms: float | None = None
    async for chunk in async_iter:
        if chunk and first_token_ms is None:
            first_token_ms = round((perf_counter() - started) * 1000, 2)
        chunks.append(chunk)
    total_ms = round((perf_counter() - started) * 1000, 2)
    return "".join(chunks).strip(), first_token_ms, total_ms


async def run_groq_direct(run_id: int) -> RunResult:
    provider = GroqProvider()
    trace: dict[str, object] = {"request_id": f"groq-direct-{run_id}"}
    try:
        response, first_token_ms, total_ms = await _collect_stream(
            provider.stream(
                instructions="Answer clearly and professionally.",
                input_text=PROMPT,
                trace=trace,
            )
        )
        return RunResult(
            name=f"groq_direct_{run_id}",
            status="ok",
            provider="groq",
            model=str(trace.get("model") or settings.groq_model),
            first_token_ms=first_token_ms,
            total_ms=total_ms,
            words=len(response.split()),
            details=dict(trace),
            response=response,
        )
    except Exception as exc:  # noqa: BLE001
        return RunResult(
            name=f"groq_direct_{run_id}",
            status=f"error:{exc.__class__.__name__}",
            provider="groq",
            model=settings.groq_model,
            first_token_ms=None,
            total_ms=None,
            words=0,
            details={"error": repr(exc), **trace},
            response="",
        )


class _FakePipeline:
    async def stream(self, effective_message: str, context: dict, trace: dict | None = None) -> AsyncIterator[str]:
        async for chunk in stream_text(
            instructions=context["instructions"],
            input_text=context["input_text"],
            trace=trace,
        ):
            yield chunk


class _FakeOrchestrator:
    def __init__(self, db) -> None:
        self.response_pipeline = _FakePipeline()

    def prepare_stream_request(self, *, user_id: str, message: str, conversation_id: str | None, file_ids: list[str]):
        return {
            "mode": "stream",
            "effective_message": message,
            "context": {
                "instructions": "Answer clearly and professionally.",
                "input_text": message,
            },
            "observability": {
                "intent_ms": 5.0,
                "retrieval_time_ms": 0.0,
                "context_tokens": 0,
                "prepare_ms": 5.0,
                "retrieval_scope": "none",
                "retrieval_sources": [],
            },
        }

    def finalize_stream_response(self, prepared: dict, response_text: str):
        trace = prepared.get("stream_trace", {})
        return {
            "response": response_text,
            "context_summary": {
                "provider": trace.get("provider"),
                "model": trace.get("model"),
                "fallback_used": trace.get("fallback_used"),
                "fallback_from": trace.get("fallback_from"),
                "request_id": trace.get("request_id"),
                "upstream_ttft_ms": trace.get("first_token_ms"),
                "endpoint_ttft_ms": trace.get("endpoint_ttft_ms"),
                "total_time_ms": trace.get("total_time_ms"),
                "context_tokens": trace.get("context_tokens"),
                "output_tokens": trace.get("output_tokens"),
                "retrieval_time_ms": trace.get("retrieval_time_ms"),
                "provider_connect_ms": trace.get("provider_connect_ms"),
                "provider_generation_ms": trace.get("provider_generation_ms"),
                "stream_opened": trace.get("stream_opened"),
                "stream_completed": trace.get("stream_completed"),
                "stream_cancelled": trace.get("stream_cancelled"),
                "stream_error_type": trace.get("stream_error_type"),
                "fallback_started": trace.get("fallback_started"),
                "fallback_provider": trace.get("fallback_provider"),
            },
        }


class _FakeAudit:
    def __init__(self, db) -> None:
        self.db = db

    def record(self, **kwargs) -> None:
        return None


async def run_stream_endpoint(run_id: int) -> RunResult:
    original_orchestrator = ceaser_routes.CeaserOrchestrator
    original_audit = ceaser_routes.AuditService
    app.dependency_overrides[ceaser_routes.get_current_user] = lambda: SimpleNamespace(id="test-user")
    app.dependency_overrides[ceaser_routes.get_db] = lambda: None
    ceaser_routes.CeaserOrchestrator = _FakeOrchestrator
    ceaser_routes.AuditService = _FakeAudit
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            started = perf_counter()
            first_token_ms: float | None = None
            response_text = ""
            complete_payload: dict | None = None
            async with client.stream("POST", "/ceaser/chat/stream", json={"message": PROMPT, "file_ids": []}) as response:
                current_event: str | None = None
                async for line in response.aiter_lines():
                    if line.startswith("event: "):
                        current_event = line[7:].strip()
                        continue
                    if not line.startswith("data: "):
                        continue
                    if current_event == "token":
                        response_text += line[6:]
                    if first_token_ms is None and response_text:
                        first_token_ms = round((perf_counter() - started) * 1000, 2)
                    if current_event == "complete":
                        complete_payload = json.loads(line[6:])
            total_ms = round((perf_counter() - started) * 1000, 2)
            context_summary = (complete_payload or {}).get("context_summary", {})
            return RunResult(
                name=f"endpoint_stream_{run_id}",
                status="ok" if complete_payload else "error:no_complete",
                provider=context_summary.get("provider"),
                model=context_summary.get("model"),
                first_token_ms=first_token_ms,
                total_ms=total_ms,
                words=len(response_text.split()),
                details=context_summary,
                response=response_text,
            )
    except Exception as exc:  # noqa: BLE001
        return RunResult(
            name=f"endpoint_stream_{run_id}",
            status=f"error:{exc.__class__.__name__}",
            provider=None,
            model=None,
            first_token_ms=None,
            total_ms=None,
            words=0,
            details={"error": repr(exc)},
            response="",
        )
    finally:
        ceaser_routes.CeaserOrchestrator = original_orchestrator
        ceaser_routes.AuditService = original_audit
        app.dependency_overrides.clear()


async def run_forced_fallback() -> RunResult:
    original_stream = GroqProvider.stream

    async def _forced_failure(self, **kwargs):  # noqa: ANN001
        raise AIServiceUnavailableError(
            "forced groq failure",
            retryable=True,
            provider="groq",
            category="provider_unavailable",
        )
        yield ""

    GroqProvider.stream = _forced_failure
    trace: dict[str, object] = {"request_id": f"forced-fallback-{uuid.uuid4().hex[:8]}"}
    try:
        response, first_token_ms, total_ms = await _collect_stream(
            stream_text(
                instructions="Answer clearly and professionally.",
                input_text=PROMPT,
                trace=trace,
            )
        )
        return RunResult(
            name="forced_fallback",
            status="ok",
            provider=str(trace.get("provider")),
            model=str(trace.get("model")),
            first_token_ms=first_token_ms,
            total_ms=total_ms,
            words=len(response.split()),
            details=dict(trace),
            response=response,
        )
    except Exception as exc:  # noqa: BLE001
        return RunResult(
            name="forced_fallback",
            status=f"error:{exc.__class__.__name__}",
            provider=str(trace.get("provider")) if trace.get("provider") else None,
            model=str(trace.get("model")) if trace.get("model") else None,
            first_token_ms=None,
            total_ms=None,
            words=0,
            details={"error": repr(exc), **trace},
            response="",
        )
    finally:
        GroqProvider.stream = original_stream


async def run_cancellation_test() -> RunResult:
    provider = GroqProvider()
    trace: dict[str, object] = {"request_id": f"cancel-{uuid.uuid4().hex[:8]}"}
    generator = provider.stream(
        instructions="Answer clearly and professionally.",
        input_text=PROMPT,
        trace=trace,
    )
    started = perf_counter()
    first_chunk = ""
    try:
        async for chunk in generator:
            first_chunk = chunk
            break
        await generator.aclose()
        total_ms = round((perf_counter() - started) * 1000, 2)
        return RunResult(
            name="cancellation",
            status="ok",
            provider="groq",
            model=settings.groq_model,
            first_token_ms=total_ms if first_chunk else None,
            total_ms=total_ms,
            words=len(first_chunk.split()),
            details=dict(trace),
            response=first_chunk,
        )
    except Exception as exc:  # noqa: BLE001
        return RunResult(
            name="cancellation",
            status=f"error:{exc.__class__.__name__}",
            provider="groq",
            model=settings.groq_model,
            first_token_ms=None,
            total_ms=None,
            words=0,
            details={"error": repr(exc), **trace},
            response="",
        )


async def run_non_2xx_test() -> RunResult:
    import app.intelligence.ai.llm.groq_provider as groq_module

    original_client = groq_module.httpx.AsyncClient

    class _FakeStreamContext:
        def __init__(self) -> None:
            request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
            self.response = httpx.Response(429, request=request, content=b'{"error":"rate_limited"}')

        async def __aenter__(self):
            return self.response

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            return None

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def stream(self, *args, **kwargs):
            return _FakeStreamContext()

    groq_module.httpx.AsyncClient = _FakeAsyncClient
    trace: dict[str, object] = {"request_id": f"non-2xx-{uuid.uuid4().hex[:8]}"}
    try:
        provider = GroqProvider()
        await _collect_stream(
            provider.stream(
                instructions="Answer clearly and professionally.",
                input_text=PROMPT,
                trace=trace,
            )
        )
        return RunResult(
            name="non_2xx",
            status="error:unexpected_success",
            provider="groq",
            model=settings.groq_model,
            first_token_ms=None,
            total_ms=None,
            words=0,
            details=dict(trace),
            response="",
        )
    except Exception as exc:  # noqa: BLE001
        return RunResult(
            name="non_2xx",
            status=f"error:{exc.__class__.__name__}",
            provider="groq",
            model=settings.groq_model,
            first_token_ms=None,
            total_ms=None,
            words=0,
            details={"error": repr(exc), **trace},
            response="",
        )
    finally:
        groq_module.httpx.AsyncClient = original_client


def diagnose_huggingface() -> dict:
    base_url = settings.huggingface_base_url.rstrip("/")
    parsed = urlparse(base_url)
    hostname = parsed.hostname or "<invalid-host>"
    try:
        socket.getaddrinfo(hostname, parsed.port or 443)
        dns = "ok"
        dns_error = None
    except Exception as exc:  # noqa: BLE001
        dns = "failed"
        dns_error = repr(exc)
    return {
        "base_url": base_url,
        "hostname": hostname,
        "model": settings.huggingface_model,
        "api_key_present": bool(settings.huggingface_api_key),
        "dns_resolution": dns,
        "dns_error": dns_error,
    }


async def main() -> int:
    results = {
        "groq_direct": [asdict(await run_groq_direct(index)) for index in range(1, 4)],
        "endpoint_stream": [asdict(await run_stream_endpoint(index)) for index in range(1, 4)],
        "forced_fallback": asdict(await run_forced_fallback()),
        "cancellation": asdict(await run_cancellation_test()),
        "non_2xx": asdict(await run_non_2xx_test()),
        "huggingface": diagnose_huggingface(),
        "router_order": ai_provider_service.llm.router.last_selected,
    }
    print(json.dumps(results, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
