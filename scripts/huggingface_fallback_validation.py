from __future__ import annotations

import asyncio
import json
import os
import socket
import uuid
from dataclasses import asdict, dataclass
from time import perf_counter
from types import SimpleNamespace
from urllib.parse import urlparse

import httpx

from app.api.ceaser import routes as ceaser_routes
from app.core.config.settings import settings
from app.intelligence.ai.errors import AIServiceUnavailableError
from app.intelligence.ai.llm.groq_provider import GroqProvider
from app.intelligence.ai.llm.huggingface_provider import HuggingFaceProvider
from app.intelligence.ai.sync import stream_text
from app.main import app


PROMPT = "Explain Retrieval-Augmented Generation in exactly three clear paragraphs and give one practical CEASER example."


@dataclass
class TestResult:
    name: str
    status: str
    provider: str | None
    model: str | None
    base_url: str | None
    hostname: str | None
    dns_result: str | None
    http_status: int | None
    connect_ms: float | None
    first_token_ms: float | None
    total_ms: float | None
    error_category: str | None
    response: str


def _dns_result(hostname: str | None) -> str:
    if not hostname:
        return "invalid_host"
    try:
        socket.getaddrinfo(hostname, 443)
        return "ok"
    except Exception as exc:  # noqa: BLE001
        return f"failed:{exc.__class__.__name__}"


async def _collect_stream(stream) -> tuple[str, float | None, float]:  # noqa: ANN001
    chunks: list[str] = []
    started = perf_counter()
    first_token_ms: float | None = None
    async for chunk in stream:
        if chunk and first_token_ms is None:
            first_token_ms = round((perf_counter() - started) * 1000, 2)
        chunks.append(chunk)
    total_ms = round((perf_counter() - started) * 1000, 2)
    return "".join(chunks).strip(), first_token_ms, total_ms


async def direct_request(run_id: int) -> TestResult:
    provider = HuggingFaceProvider()
    base_url = settings.huggingface_base_url.rstrip("/")
    hostname = urlparse(base_url).hostname
    dns_result = _dns_result(hostname)
    trace: dict[str, object] = {}
    try:
        response, first_token_ms, total_ms = await _collect_stream(
            provider.stream(
                instructions="Answer clearly and professionally.",
                input_text=PROMPT,
                trace=trace,
            )
        )
        return TestResult(
            name=f"direct_{run_id}",
            status="ok",
            provider="huggingface",
            model=settings.huggingface_model,
            base_url=base_url,
            hostname=hostname,
            dns_result=dns_result,
            http_status=200,
            connect_ms=trace.get("provider_connect_ms"),
            first_token_ms=first_token_ms,
            total_ms=total_ms,
            error_category=None,
            response=response,
        )
    except AIServiceUnavailableError as exc:
        return TestResult(
            name=f"direct_{run_id}",
            status="error",
            provider="huggingface",
            model=settings.huggingface_model,
            base_url=base_url,
            hostname=hostname,
            dns_result=dns_result,
            http_status=None,
            connect_ms=None,
            first_token_ms=None,
            total_ms=None,
            error_category=exc.category,
            response="",
        )


class _FakePipeline:
    async def stream(self, effective_message: str, context: dict, trace: dict | None = None):
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
            "context_summary": trace,
        }


class _FakeAudit:
    def __init__(self, db) -> None:
        self.db = db

    def record(self, **kwargs) -> None:
        return None


async def provider_through_ceaser(run_id: int) -> TestResult:
    original_orchestrator = ceaser_routes.CeaserOrchestrator
    original_audit = ceaser_routes.AuditService
    original_candidates = ceaser_routes.CeaserOrchestrator
    app.dependency_overrides[ceaser_routes.get_current_user] = lambda: SimpleNamespace(id="test-user")
    app.dependency_overrides[ceaser_routes.get_db] = lambda: None
    ceaser_routes.CeaserOrchestrator = _FakeOrchestrator
    ceaser_routes.AuditService = _FakeAudit
    router = __import__("app.intelligence.ai.ai_provider_service", fromlist=["ai_provider_service"]).ai_provider_service.llm.router
    saved_candidates = router.candidates
    router.candidates = lambda max_count=2: [("huggingface", HuggingFaceProvider())]
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            current_event = None
            response_text = ""
            complete_payload = None
            started = perf_counter()
            first_token_ms = None
            async with client.stream("POST", "/ceaser/chat/stream", json={"message": PROMPT, "file_ids": []}) as response:
                async for line in response.aiter_lines():
                    if line.startswith("event: "):
                        current_event = line[7:].strip()
                        continue
                    if not line.startswith("data: "):
                        continue
                    if current_event == "token":
                        response_text += line[6:]
                        if first_token_ms is None:
                            first_token_ms = round((perf_counter() - started) * 1000, 2)
                    elif current_event == "complete":
                        complete_payload = json.loads(line[6:])
            total_ms = round((perf_counter() - started) * 1000, 2)
            trace = (complete_payload or {}).get("context_summary", {})
            return TestResult(
                name=f"provider_{run_id}",
                status="ok" if complete_payload else "error",
                provider=trace.get("provider"),
                model=trace.get("model"),
                base_url=settings.huggingface_base_url.rstrip("/"),
                hostname=urlparse(settings.huggingface_base_url.rstrip("/")).hostname,
                dns_result=_dns_result(urlparse(settings.huggingface_base_url.rstrip("/")).hostname),
                http_status=200 if complete_payload else None,
                connect_ms=trace.get("provider_connect_ms"),
                first_token_ms=first_token_ms,
                total_ms=total_ms,
                error_category=trace.get("stream_error_type"),
                response=response_text,
            )
    except Exception as exc:  # noqa: BLE001
        return TestResult(
            name=f"provider_{run_id}",
            status=f"error:{exc.__class__.__name__}",
            provider="huggingface",
            model=settings.huggingface_model,
            base_url=settings.huggingface_base_url.rstrip("/"),
            hostname=urlparse(settings.huggingface_base_url.rstrip("/")).hostname,
            dns_result=_dns_result(urlparse(settings.huggingface_base_url.rstrip("/")).hostname),
            http_status=None,
            connect_ms=None,
            first_token_ms=None,
            total_ms=None,
            error_category="exception",
            response="",
        )
    finally:
        router.candidates = saved_candidates
        ceaser_routes.CeaserOrchestrator = original_orchestrator
        ceaser_routes.AuditService = original_audit
        app.dependency_overrides.clear()


async def forced_fallback(run_id: int) -> TestResult:
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
    trace: dict[str, object] = {"request_id": f"forced-fallback-{run_id}"}
    try:
        response, first_token_ms, total_ms = await _collect_stream(
            stream_text(
                instructions="Answer clearly and professionally.",
                input_text=PROMPT,
                trace=trace,
            )
        )
        return TestResult(
            name=f"fallback_{run_id}",
            status="ok",
            provider=str(trace.get("provider")),
            model=str(trace.get("model")),
            base_url=settings.huggingface_base_url.rstrip("/"),
            hostname=urlparse(settings.huggingface_base_url.rstrip("/")).hostname,
            dns_result=_dns_result(urlparse(settings.huggingface_base_url.rstrip("/")).hostname),
            http_status=200,
            connect_ms=trace.get("provider_connect_ms"),
            first_token_ms=first_token_ms,
            total_ms=total_ms,
            error_category=None,
            response=response,
        )
    except AIServiceUnavailableError as exc:
        return TestResult(
            name=f"fallback_{run_id}",
            status="error",
            provider=str(trace.get("provider")) if trace.get("provider") else "huggingface",
            model=str(trace.get("model")) if trace.get("model") else settings.huggingface_model,
            base_url=settings.huggingface_base_url.rstrip("/"),
            hostname=urlparse(settings.huggingface_base_url.rstrip("/")).hostname,
            dns_result=_dns_result(urlparse(settings.huggingface_base_url.rstrip("/")).hostname),
            http_status=None,
            connect_ms=trace.get("provider_connect_ms"),
            first_token_ms=None,
            total_ms=None,
            error_category=exc.category,
            response="",
        )
    finally:
        GroqProvider.stream = original_stream


async def invalid_token_test() -> TestResult:
    original_key = settings.huggingface_api_key
    settings.huggingface_api_key = "hf_invalid_token"
    try:
        return await direct_request(0)
    finally:
        settings.huggingface_api_key = original_key


async def invalid_model_test() -> TestResult:
    original_model = settings.huggingface_model
    settings.huggingface_model = "does-not-exist/invalid-model"
    try:
        return await direct_request(0)
    finally:
        settings.huggingface_model = original_model


async def dns_failure_test() -> TestResult:
    original_url = settings.huggingface_base_url
    settings.huggingface_base_url = "https://hf-invalid-hostname.ceaser.invalid/v1/chat/completions"
    try:
        return await direct_request(0)
    finally:
        settings.huggingface_base_url = original_url


async def main() -> int:
    diagnostics = {
        "proxy_env": {
            "HTTP_PROXY": bool(os.environ.get("HTTP_PROXY")),
            "HTTPS_PROXY": bool(os.environ.get("HTTPS_PROXY")),
            "ALL_PROXY": bool(os.environ.get("ALL_PROXY")),
            "NO_PROXY": bool(os.environ.get("NO_PROXY")),
        },
        "direct_runs": [asdict(await direct_request(i)) for i in range(1, 4)],
        "provider_runs": [asdict(await provider_through_ceaser(i)) for i in range(1, 4)],
        "fallback_runs": [asdict(await forced_fallback(i)) for i in range(1, 4)],
        "invalid_token": asdict(await invalid_token_test()),
        "invalid_model": asdict(await invalid_model_test()),
        "dns_failure": asdict(await dns_failure_test()),
    }
    print(json.dumps(diagnostics, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
