import asyncio
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
from app.services.conversation_service import ConversationService
from app.services.orchestrator import CeaserOrchestrator
from app.services.rich_response_service import RichResponseService
from app.services.credit_service import CreditService, InsufficientCreditsError

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
    user_id = user.id
    billing_id = f"chat:{payload.request_id or uuid.uuid4().hex}"
    credits = CreditService(db)
    try:
        reservation = credits.reserve(user_id, billing_id, "ai_conversation")
    except InsufficientCreditsError as exc:
        raise HTTPException(status_code=402, detail="Insufficient CEASER credits.") from exc
    try:
        desktop_fast = _maybe_desktop_fast_response(payload)
        if desktop_fast is not None:
            credits.settle(user_id, billing_id, reservation.estimated_credits, meaningful_output=True)
            return desktop_fast
        response = CeaserOrchestrator(db).handle_message(
            user_id=user_id,
            message=payload.message,
            conversation_id=payload.conversation_id,
            file_ids=payload.file_ids,
            request_id=payload.request_id,
            parent_message_id=payload.parent_message_id,
            device_id=payload.device_id,
            desktop_file_context=payload.desktop_file_context,
            model_preference=payload.model_preference,
            force_live_web_search=payload.force_live_web_search,
            response_mode=payload.response_mode,
            image_model_preference=payload.image_model_preference,
        )
        response["rich_response"] = RichResponseService.compose(response,user_id=user_id,task_id=payload.request_id).model_dump(mode="json")
        AuditService(db).record(
            user_id=user_id,
            action="message_created",
            resource_type="conversation",
            resource_id=payload.conversation_id,
            metadata={"selected_agents": response.get("selected_agents", []), "memory_count": len(response.get("memories_used", []))},
        )
        credits.settle(user_id, billing_id, reservation.estimated_credits, meaningful_output=bool(response.get("response")))
        return response
    except ValueError as exc:
        db.rollback()
        credits.release(user_id, billing_id)
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        credits.release(user_id, billing_id)
        raise


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
        "notion", "github", "calendar", "task", "email", "mail", "upload", "post", "publish",
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
    billing_id = f"chat:{payload.request_id or task_id}"
    credits = CreditService(db)
    reserved = False
    try:
        credits.reserve(user_id, billing_id, "ai_conversation")
        reserved = True
        response = CeaserOrchestrator(db).handle_message(
            user_id=user_id,
            message=payload.message,
            conversation_id=payload.conversation_id,
            file_ids=payload.file_ids,
            request_id=payload.request_id,
            parent_message_id=payload.parent_message_id,
            device_id=payload.device_id,
            desktop_file_context=payload.desktop_file_context,
            model_preference=payload.model_preference,
            force_live_web_search=payload.force_live_web_search,
            response_mode=payload.response_mode,
            image_model_preference=payload.image_model_preference,
        )
        credits.settle(user_id, billing_id, settings.credit_costs.get("ai_conversation", 5), meaningful_output=bool(response))
        reserved = False
        background_task_store.set_result(task_id, response)
    except InsufficientCreditsError:
        background_task_store.set_error(task_id, "Insufficient CEASER credits.")
    except Exception:
        logger.exception("ceaser_background_task_failed task_id=%s user_id=%s", task_id, user_id)
        background_task_store.set_error(task_id, "We couldn't complete your request. Please try again.")
    finally:
        if reserved:
            credits.release(user_id, billing_id)
        db.close()


@router.post("/chat/stream")
async def ceaser_chat_stream(payload: CeaserChatRequest, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    route_entered = perf_counter()
    user_id = user.id
    message = payload.message
    conversation_id = payload.conversation_id
    file_ids = list(payload.file_ids)
    request_id = str(uuid.uuid4())
    billing_id = f"chat:{payload.request_id or request_id}"
    credits = CreditService(db)
    try:
        reserve_started = perf_counter()
        reservation = credits.reserve(user.id, billing_id, "ai_conversation")
        logger.info("ceaser_stream_stage request_id=%s stage=credits_reserved duration_ms=%.2f", request_id, (perf_counter() - reserve_started) * 1000)
    except InsufficientCreditsError as exc:
        raise HTTPException(status_code=402, detail="Insufficient CEASER credits.") from exc
    # Keep only immutable primitives across the async SSE lifetime. The ORM
    # reservation is committed/refreshed here and must not be dereferenced
    # after the request session has expired or been detached.
    reservation_estimated_credits = int(reservation.estimated_credits)
    # A new chat is created authoritatively inside the stream request. This
    # removes the frontend's blocking create-conversation round trip while
    # preserving one durable conversation and the existing ownership checks.
    if not conversation_id:
        conversation_started = perf_counter()
        conversation_id = ConversationService(db).create(user_id=user.id).id
        logger.info("ceaser_stream_stage request_id=%s stage=conversation_created duration_ms=%.2f", request_id, (perf_counter() - conversation_started) * 1000)
    request_received = route_entered
    logger.info("ceaser_latency request_id=%s route_entry_ms=0 conversation_id=%s", request_id, conversation_id)
    logger.info("ceaser_stream_stage request_id=%s stage=authentication_complete user_id=%s", request_id, user_id)

    def event(event_type: str, data: dict | str) -> str:
        payload_text = data if isinstance(data, str) else json.dumps(data, ensure_ascii=True)
        return f"event: {event_type}\ndata: {payload_text}\n\n"

    async def stream() -> AsyncIterator[str]:
        started = request_received
        stage_marks: dict[str, float] = {"start": started}
        trace: dict[str, object] = {"request_id": request_id}
        first_sse_token_logged = False
        completed_meaningfully = False
        try:
            yield event("response.started", {"id": request_id, "status": "streaming", "conversation_id": conversation_id})
            yield event("activity", {"event_id": f"evt_{request_id}_start", "task_id": request_id, "agent": "CEASER", "category": "response", "stage": "understanding", "status": "running", "title": "Understanding request", "safe_metadata": {}})
            yield event("status", {"state": "received"})
            yield event("status", {"state": "understanding_request"})
            orchestrator = CeaserOrchestrator(db)
            trace["agent_started_ms"] = round((perf_counter() - started) * 1000, 2)
            logger.info("ceaser_latency request_id=%s agent_started_ms=%s", request_id, trace["agent_started_ms"])
            logger.info("ceaser_stream_stage request_id=%s stage=retrieval_started", request_id)
            prepared = await asyncio.to_thread(
                orchestrator.prepare_stream_request,
                user_id=user_id,
                message=message,
                conversation_id=conversation_id,
                file_ids=file_ids,
                request_id=payload.request_id or request_id,
                parent_message_id=payload.parent_message_id,
                model_preference=payload.model_preference,
                force_live_web_search=payload.force_live_web_search,
            )
            stage_marks["prepared"] = perf_counter()
            trace["retrieval_time_ms"] = prepared.get("observability", {}).get("retrieval_time_ms")
            trace["routing_ms"] = prepared.get("observability", {}).get("routing_ms")
            trace["tool_calls_ms"] = prepared.get("observability", {}).get("tool_calls_ms")
            trace["web_search_requested"] = prepared.get("observability", {}).get("web_search_requested")
            trace["internal_context_found"] = prepared.get("observability", {}).get("internal_context_found")
            trace["memory_match_count"] = prepared.get("observability", {}).get("memory_match_count")
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
                "ceaser_stream_stage request_id=%s stage=context_complete context_tokens=%s prepare_ms=%s routing_ms=%s tool_calls_ms=%s web_search_requested=%s internal_context_found=%s memory_match_count=%s context_mode=%s retrieval_scope=%s retrieval_sources=%s",
                request_id,
                prepared.get("observability", {}).get("context_tokens"),
                prepared.get("observability", {}).get("prepare_ms"),
                trace.get("routing_ms"),
                trace.get("tool_calls_ms"),
                trace.get("web_search_requested"),
                trace.get("internal_context_found"),
                trace.get("memory_match_count"),
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
                rich = RichResponseService.compose(response,user_id=user_id,task_id=request_id).model_dump(mode="json")
                response["rich_response"] = rich
                for block in rich["blocks"]: yield event("block.created", block)
                yield event("response.completed", rich)
                yield event("complete", response)
                completed_meaningfully = bool(response.get("response"))
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
                if not first_sse_token_logged:
                    token_received_at = perf_counter()
                    trace["endpoint_ttft_ms"] = round((perf_counter() - started) * 1000, 2)
                    logger.info("ceaser_latency request_id=%s first_token_ms=%s", request_id, trace["endpoint_ttft_ms"])
                    logger.info(
                        "ceaser_stream_stage request_id=%s stage=first_sse_token endpoint_ttft_ms=%s",
                        request_id,
                        trace["endpoint_ttft_ms"],
                    )
                    first_sse_token_logged = True
                    yield event("token", chunk)
                    trace["first_token_forwarding_ms"] = round((perf_counter() - token_received_at) * 1000, 2)
                    # Durability begins only after the first chunk has been
                    # forwarded. A database commit must never delay user TTFT.
                    assistant_message = orchestrator.begin_stream_response(prepared)
                    if assistant_message:
                        orchestrator.persist_stream_response(assistant_message, response_so_far)
                        persisted_length = len(response_so_far)
                    continue
                if assistant_message and len(response_so_far) - persisted_length >= 360:
                    orchestrator.persist_stream_response(assistant_message, response_so_far)
                    persisted_length = len(response_so_far)
                yield event("token", chunk)
            response_text = "".join(chunks).strip()
            trace["output_tokens"] = max(1, round(len(response_text) / 4)) if response_text else 0
            trace["total_time_ms"] = round((perf_counter() - started) * 1000, 2)
            prepared["stream_trace"] = trace
            response = orchestrator.finalize_stream_response(prepared, response_text, assistant_message=assistant_message)
            if trace.get("structural_completion_blocked"):
                response["status"] = "partial"
                response["completion_warning"] = "The code artifact needs continuation before it is complete."
                logger.warning(
                    "ceaser_stream_stage request_id=%s stage=structural_completion_blocked artifact_type=%s continuation_count=%s",
                    request_id,
                    trace.get("artifact_type"),
                    trace.get("continuation_count", 0),
                )
            rich = RichResponseService.compose(response,user_id=user_id,task_id=request_id).model_dump(mode="json")
            response["rich_response"] = rich
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
            for block in rich["blocks"]: yield event("block.created", block)
            yield event("activity", rich["activity"][0])
            yield event("response.completed", rich)
            yield event("complete", response)
            completed_meaningfully = bool(response.get("response"))
            logger.info("ceaser_stream_stage request_id=%s stage=request_complete total_ms=%s", request_id, trace.get("total_time_ms"))
        except ValueError as exc:
            yield event("response.failed", {"id": request_id, "status": "failed", "error": {"category": "validation", "message": str(exc), "retryable": False}})
            yield event("error", {"message": str(exc)})
        except Exception:
            db.rollback()
            logger.exception("ceaser_chat_stream_failed user_id=%s conversation_id=%s", user_id, conversation_id)
            yield event("response.failed", {"id": request_id, "status": "failed", "error": {"category": "internal", "message": "We couldn't complete your request. Please try again.", "retryable": True}})
            yield event("error", {"message": "We couldn't complete your request. Please try again."})
        finally:
            try:
                if completed_meaningfully:
                    credits.settle(user_id, billing_id, reservation_estimated_credits, meaningful_output=True)
                else:
                    db.rollback()
                    credits.release(user_id, billing_id)
            except Exception:
                # Tokens may already be visible. Keep the user response intact
                # while recording the accounting failure for repair/audit.
                db.rollback()
                logger.exception("ceaser_stream_settlement_failed user_id=%s billing_id=%s", user_id, billing_id)

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
