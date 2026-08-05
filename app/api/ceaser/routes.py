import logging
import uuid
from typing import Annotated

import json
from collections.abc import AsyncIterator
from time import perf_counter

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database.session import SessionLocal, get_db
from app.core.security.dependencies import get_current_user
from app.intelligence.ai.sync import generate_text_sync
from app.models.user import User
from app.schemas.ceaser import CeaserChatRequest, CeaserChatResponse
from app.services.audit_service import AuditService
from app.services.background_task_service import background_task_store
from app.services.orchestrator import CeaserOrchestrator

router = APIRouter(prefix="/ceaser", tags=["ceaser"])
logger = logging.getLogger(__name__)


class CeaserDemoRequest(BaseModel):
    message: str = Field(min_length=1, max_length=14000)


class CeaserDemoResponse(BaseModel):
    response: str
    source: str = "live_backend"


@router.post("/demo", response_model=CeaserDemoResponse)
def ceaser_public_demo(payload: CeaserDemoRequest):
    instructions = (
        "You are CEASER, an AI operating system product demo. "
        "Generate a concise, polished, useful answer for a public landing-page demo. "
        "Use the provided scenario/context exactly. Do not ask for missing context unless the prompt truly has none. "
        "Do not mention backend, APIs, tokens, providers, or internal implementation. "
        "Keep the answer structured, specific, and under 350 words."
    )
    response = generate_text_sync(
        instructions=instructions,
        input_text=payload.message,
        temperature=0.35,
        max_output_tokens=650,
    )
    return CeaserDemoResponse(response=response)


@router.post("/chat", response_model=CeaserChatResponse)
def ceaser_chat(payload: CeaserChatRequest, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    try:
        desktop_fast = _maybe_desktop_fast_response(payload)
        if desktop_fast is not None:
            return desktop_fast
        response = CeaserOrchestrator(db).handle_message(
            user_id=user.id,
            message=payload.message,
            conversation_id=payload.conversation_id,
            file_ids=payload.file_ids,
            request_id=payload.request_id,
            parent_message_id=payload.parent_message_id,
        )
        AuditService(db).record(
            user_id=user.id,
            action="message_created",
            resource_type="conversation",
            resource_id=payload.conversation_id,
            metadata={"selected_agents": response.get("selected_agents", []), "memory_count": len(response.get("memories_used", []))},
        )
        return response
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _maybe_desktop_fast_response(payload: CeaserChatRequest) -> dict | None:
    if payload.source != "desktop_companion" or not payload.voice:
        return None
    if payload.conversation_id or payload.file_ids:
        return None
    message = (payload.original_message or payload.message or "").strip()
    if not message:
        return None
    normalized = message.lower()
    heavy_terms = (
        "my ", "me ", "project", "file", "document", "pdf", "report", "memory",
        "notion", "github", "calendar", "task", "email", "mail", "upload",
        "delete", "restore", "rename", "latest", "connected", "workspace",
        "summarize my", "what do i have", "what is my", "who am i",
    )
    current_terms = ("current", "latest", "today", "now", "news", "weather", "score", "price", "stock", "stats")
    if any(term in normalized for term in heavy_terms + current_terms):
        return None
    started = perf_counter()
    instructions = (
        "You are CEASER Desktop Companion. Answer the user's voice question directly and quickly. "
        "Keep the response concise, accurate, and useful for spoken playback. "
        "Use short paragraphs or bullets only when helpful. "
        "Do not mention backend, providers, sources, or implementation. "
        "Maximum 180 words."
    )
    response = generate_text_sync(
        instructions=instructions,
        input_text=message,
        temperature=0.35,
        max_output_tokens=360,
    ).strip()
    elapsed_ms = round((perf_counter() - started) * 1000, 2)
    logger.info(
        "ceaser_desktop_fast_response request_id=%s elapsed_ms=%s input_chars=%s output_chars=%s",
        payload.request_id,
        elapsed_ms,
        len(message),
        len(response),
    )
    return {
        "scope": "desktop_fast_ai",
        "conversation_id": None,
        "selected_agents": ["Ceaser"],
        "contributions": [],
        "contribution_summary": "Desktop fast response generated.",
        "memories_used": [],
        "research": None,
        "workflow": None,
        "context_summary": {
            "retrieval_scope": "desktop_fast_ai",
            "retrieval_sources": ["none"],
            "retrieval_time_ms": 0,
            "context_build_ms": 0,
            "backend_fast_path_ms": elapsed_ms,
            "cache_hit": True,
        },
        "suggestions": [],
        "response": response,
    }


@router.post("/chat/background")
def ceaser_chat_background(
    payload: CeaserChatRequest,
    background_tasks: BackgroundTasks,
    user: Annotated[User, Depends(get_current_user)],
):
    task_id = str(uuid.uuid4())
    background_task_store.create(task_id, user.id)
    background_tasks.add_task(_run_chat_background_task, task_id, user.id, payload)
    return {"task_id": task_id, "status": "queued"}


@router.get("/chat/background/{task_id}")
def get_ceaser_background_task(task_id: str, user: Annotated[User, Depends(get_current_user)]):
    record = background_task_store.get(task_id)
    if not record or record.user_id != user.id:
        raise HTTPException(status_code=404, detail="Task not found.")
    return {
        "task_id": record.id,
        "status": record.status,
        "result": record.result,
        "error": record.error,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


def _run_chat_background_task(task_id: str, user_id: str, payload: CeaserChatRequest) -> None:
    background_task_store.set_running(task_id)
    db = SessionLocal()
    try:
        response = CeaserOrchestrator(db).handle_message(
            user_id=user_id,
            message=payload.message,
            conversation_id=payload.conversation_id,
            file_ids=payload.file_ids,
            request_id=payload.request_id,
            parent_message_id=payload.parent_message_id,
        )
        background_task_store.set_result(task_id, response)
    except Exception:
        logger.exception("ceaser_background_task_failed task_id=%s user_id=%s", task_id, user_id)
        background_task_store.set_error(task_id, "We couldn't complete your request. Please try again.")
    finally:
        db.close()


@router.post("/chat/stream")
async def ceaser_chat_stream(payload: CeaserChatRequest, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    user_id = user.id
    message = payload.message
    conversation_id = payload.conversation_id
    file_ids = list(payload.file_ids)
    request_id = str(uuid.uuid4())
    request_received = perf_counter()
    logger.info("ceaser_latency request_id=%s request_received_ms=0 conversation_id=%s", request_id, conversation_id)
    logger.info("ceaser_stream_stage request_id=%s stage=authentication_complete user_id=%s", request_id, user_id)

    def event(event_type: str, data: dict | str) -> str:
        payload_text = data if isinstance(data, str) else json.dumps(data, ensure_ascii=True)
        return f"event: {event_type}\ndata: {payload_text}\n\n"

    async def stream() -> AsyncIterator[str]:
        started = request_received
        stage_marks: dict[str, float] = {"start": started}
        trace: dict[str, object] = {"request_id": request_id}
        first_sse_token_logged = False
        try:
            yield event("status", {"state": "received"})
            yield event("status", {"state": "understanding_request"})
            orchestrator = CeaserOrchestrator(db)
            trace["agent_started_ms"] = round((perf_counter() - started) * 1000, 2)
            logger.info("ceaser_latency request_id=%s agent_started_ms=%s", request_id, trace["agent_started_ms"])
            logger.info("ceaser_stream_stage request_id=%s stage=retrieval_started", request_id)
            prepared = orchestrator.prepare_stream_request(
                user_id=user_id,
                message=message,
                conversation_id=conversation_id,
                file_ids=file_ids,
                request_id=payload.request_id or request_id,
                parent_message_id=payload.parent_message_id,
            )
            stage_marks["prepared"] = perf_counter()
            trace["retrieval_time_ms"] = prepared.get("observability", {}).get("retrieval_time_ms")
            trace["routing_ms"] = prepared.get("observability", {}).get("routing_ms")
            trace["tool_calls_ms"] = prepared.get("observability", {}).get("tool_calls_ms")
            trace["context_build_ms"] = prepared.get("observability", {}).get("retrieval_time_ms")
            logger.info(
                "ceaser_stream_stage request_id=%s stage=intent_complete intent_ms=%s",
                request_id,
                prepared.get("observability", {}).get("intent_ms"),
            )
            logger.info(
                "ceaser_stream_stage request_id=%s stage=retrieval_complete retrieval_time_ms=%s",
                request_id,
                prepared.get("observability", {}).get("retrieval_time_ms"),
            )
            logger.info(
                "ceaser_stream_stage request_id=%s stage=context_complete context_tokens=%s prepare_ms=%s routing_ms=%s tool_calls_ms=%s context_mode=%s retrieval_scope=%s retrieval_sources=%s",
                request_id,
                prepared.get("observability", {}).get("context_tokens"),
                prepared.get("observability", {}).get("prepare_ms"),
                trace.get("routing_ms"),
                trace.get("tool_calls_ms"),
                prepared.get("observability", {}).get("context_mode"),
                prepared.get("observability", {}).get("retrieval_scope"),
                prepared.get("observability", {}).get("retrieval_sources"),
            )

            if prepared["mode"] == "direct":
                yield event("status", {"state": "generating"})
                trace["endpoint_ttft_ms"] = round((perf_counter() - started) * 1000, 2)
                trace["total_time_ms"] = trace["endpoint_ttft_ms"]
                trace["output_tokens"] = max(1, round(len(prepared["response"]) / 4)) if prepared.get("response") else 0
                yield event("token", prepared["response"])
                first_sse_token_logged = True
                logger.info(
                    "ceaser_stream_stage request_id=%s stage=first_sse_token endpoint_ttft_ms=%s",
                    request_id,
                    trace["endpoint_ttft_ms"],
                )
                prepared["stream_trace"] = trace
                response = orchestrator.finalize_stream_response(prepared, prepared["response"])
                yield event("complete", response)
                logger.info(
                    "ceaser_latency request_id=%s request_received_ms=0 agent_started_ms=%s llm_request_sent_ms=not_applicable first_token_ms=%s last_token_ms=%s",
                    request_id,
                    trace.get("agent_started_ms"),
                    trace.get("endpoint_ttft_ms"),
                    trace.get("total_time_ms"),
                )
                logger.info("ceaser_stream_stage request_id=%s stage=request_complete total_ms=%s", request_id, trace["total_time_ms"])
                return

            yield event("status", {"state": "retrieving_context"})
            stage_marks["context_ready"] = perf_counter()
            yield event("status", {"state": "generating"})
            trace["llm_request_sent_ms"] = round((perf_counter() - started) * 1000, 2)
            logger.info("ceaser_latency request_id=%s llm_request_sent_ms=%s", request_id, trace["llm_request_sent_ms"])
            chunks: list[str] = []
            assistant_message = None
            persisted_length = 0
            async for chunk in orchestrator.response_pipeline.stream(
                prepared["message"],
                prepared["context"],
                trace=trace,
            ):
                chunks.append(chunk)
                response_so_far = "".join(chunks)
                if assistant_message is None:
                    assistant_message = orchestrator.begin_stream_response(prepared)
                # Persist the first visible text and regular checkpoints. This
                # makes a refresh recover the response instead of only its prompt.
                if assistant_message and (persisted_length == 0 or len(response_so_far) - persisted_length >= 360):
                    orchestrator.persist_stream_response(assistant_message, response_so_far)
                    persisted_length = len(response_so_far)
                if not first_sse_token_logged:
                    trace["endpoint_ttft_ms"] = round((perf_counter() - started) * 1000, 2)
                    logger.info("ceaser_latency request_id=%s first_token_ms=%s", request_id, trace["endpoint_ttft_ms"])
                    logger.info(
                        "ceaser_stream_stage request_id=%s stage=first_sse_token endpoint_ttft_ms=%s",
                        request_id,
                        trace["endpoint_ttft_ms"],
                    )
                    first_sse_token_logged = True
                yield event("token", chunk)
            response_text = "".join(chunks).strip()
            trace["output_tokens"] = max(1, round(len(response_text) / 4)) if response_text else 0
            trace["total_time_ms"] = round((perf_counter() - started) * 1000, 2)
            prepared["stream_trace"] = trace
            response = orchestrator.finalize_stream_response(prepared, response_text, assistant_message=assistant_message)
            stage_marks["complete"] = perf_counter()
            logger.info(
                "ceaser_latency request_id=%s request_received_ms=0 agent_started_ms=%s context_build_ms=%s routing_ms=%s tool_calls_ms=%s llm_request_sent_ms=%s first_token_ms=%s last_token_ms=%s",
                request_id,
                trace.get("agent_started_ms"),
                trace.get("context_build_ms"),
                trace.get("routing_ms"),
                trace.get("tool_calls_ms"),
                trace.get("llm_request_sent_ms"),
                trace.get("endpoint_ttft_ms"),
                trace.get("total_time_ms"),
            )
            logger.info(
                "ceaser_stream_trace user_id=%s conversation_id=%s prepare_ms=%s context_ms=%s provider=%s model=%s fallback=%s first_token_ms=%s total_ms=%s",
                user_id,
                conversation_id,
                round((stage_marks.get("prepared", started) - started) * 1000, 2),
                round((stage_marks.get("context_ready", stage_marks.get("prepared", started)) - stage_marks.get("prepared", started)) * 1000, 2),
                trace.get("provider"),
                trace.get("model"),
                trace.get("fallback"),
                trace.get("first_token_ms"),
                round((stage_marks["complete"] - started) * 1000, 2),
            )
            logger.info(
                "ceaser_stream_stage request_id=%s stage=generation_complete provider=%s model=%s fallback_used=%s fallback_from=%s upstream_ttft_ms=%s provider_connect_ms=%s provider_generation_ms=%s output_tokens=%s",
                request_id,
                trace.get("provider"),
                trace.get("model"),
                trace.get("fallback_used"),
                trace.get("fallback_from"),
                trace.get("first_token_ms"),
                trace.get("provider_connect_ms"),
                trace.get("provider_generation_ms"),
                trace.get("output_tokens"),
            )
            AuditService(db).record(
                user_id=user_id,
                action="message_created",
                resource_type="conversation",
                resource_id=conversation_id,
                metadata={"selected_agents": response.get("selected_agents", []), "memory_count": len(response.get("memories_used", []))},
            )
            yield event("complete", response)
            logger.info("ceaser_stream_stage request_id=%s stage=request_complete total_ms=%s", request_id, trace.get("total_time_ms"))
        except ValueError as exc:
            yield event("error", {"message": str(exc)})
        except Exception:
            logger.exception("ceaser_chat_stream_failed user_id=%s conversation_id=%s", user_id, conversation_id)
            yield event("error", {"message": "We couldn't complete your request. Please try again."})

    # Keep SSE events flowing through hosting proxies as they are produced.
    # Without no-transform / X-Accel-Buffering, a proxy can hold small token
    # events and make a genuine stream look like one delayed final response.
    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _chunk_text(text: str, max_chars: int = 120) -> list[str]:
    if not text:
        return []
    chunks: list[str] = []
    buffer = ""
    for piece in text.split():
        candidate = f"{buffer} {piece}".strip()
        if len(candidate) > max_chars and buffer:
            chunks.append(buffer)
            buffer = piece
        else:
            buffer = candidate
    if buffer:
        chunks.append(buffer)
    return chunks
