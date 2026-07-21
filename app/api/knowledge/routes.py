from __future__ import annotations

from time import perf_counter
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.config.settings import settings
from app.core.database.session import get_db
from app.core.security.dependencies import get_current_user
from app.intelligence.ai.ai_provider_service import ai_provider_service
from app.intelligence.knowledge.context_builder import context_builder
from app.intelligence.knowledge.engine import KnowledgeEngine
from app.intelligence.knowledge.embedding_service import KnowledgeEmbeddingService
from app.intelligence.knowledge.repository import KnowledgeRepository
from app.intelligence.orchestrator.intent_engine import intent_engine
from app.intelligence.orchestrator.models import RequestContext
from app.intelligence.orchestrator.request_orchestrator import RequestOrchestrator
from app.intelligence.orchestrator.retrieval_planner import retrieval_planner
from app.models.user import User
from app.schemas.knowledge import (
    ContextBuildRequest,
    ContextBuildResponse,
    KnowledgeChunkRead,
    KnowledgeIngestTextRequest,
    KnowledgeSearchRequest,
    KnowledgeSearchResponse,
    KnowledgeSourceRead,
)

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


@router.get("/sources", response_model=list[KnowledgeSourceRead])
def list_sources(user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    return KnowledgeRepository(db).list_sources(user_id=user.id)


@router.post("/ingest/text", response_model=KnowledgeSourceRead, status_code=status.HTTP_201_CREATED)
async def ingest_text(payload: KnowledgeIngestTextRequest, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    source = KnowledgeRepository(db).ingest_text(
        user_id=user.id,
        title=payload.title,
        content=payload.content,
        source_type=payload.source_type,
        project_id=payload.project_id,
        conversation_id=payload.conversation_id,
        metadata=payload.metadata,
    )
    if settings.knowledge_auto_embed:
        await KnowledgeEmbeddingService(db).embed_source(user_id=user.id, source_id=source.id)
    db.commit()
    db.refresh(source)
    return source


@router.post("/search", response_model=KnowledgeSearchResponse)
async def search(payload: KnowledgeSearchRequest, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    started = perf_counter()
    repo = KnowledgeRepository(db)
    chunks = await repo.hybrid_search_chunks(
        user_id=user.id,
        query=payload.query,
        project_id=payload.project_id,
        source_id=payload.source_id,
        limit=payload.limit,
    )
    repo.log_retrieval(
        user_id=user.id,
        intent="manual_search",
        provider_names=["documents"],
        chunk_ids=[chunk.id for chunk in chunks],
        source_ids=list({chunk.source_id for chunk in chunks}),
        latency_ms=round((perf_counter() - started) * 1000),
    )
    db.commit()
    return KnowledgeSearchResponse(
        items=[
            KnowledgeChunkRead(
                id=chunk.id,
                source_id=chunk.source_id,
                content=chunk.content,
                section_title=chunk.section_title,
                relevance_score=0.75,
                metadata=chunk.extra_metadata,
            )
            for chunk in chunks
        ],
        provider_names=["documents"],
        latency_ms=round((perf_counter() - started) * 1000),
    )


@router.post("/context", response_model=ContextBuildResponse)
async def build_context(payload: ContextBuildRequest, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    request = RequestContext(
        user_id=user.id,
        message=payload.message,
        conversation_id=payload.conversation_id,
        project_id=payload.project_id,
        active_screen=payload.active_screen,
        interaction_mode=payload.interaction_mode,
    )
    intent = await intent_engine.classify(request)
    plan = await retrieval_planner.build(request=request, intent=intent)
    plan.providers = [provider for provider in plan.providers if provider.provider == "documents"]
    for provider in plan.providers:
        provider.limit = payload.limit
    items = await KnowledgeEngine(db).retrieve(request=request, plan=plan)
    context = context_builder.build(request=request, items=items)
    db.commit()
    return ContextBuildResponse(
        intent=intent.value,
        output_format=plan.output_format,
        needs_generation=plan.needs_generation,
        evidence_text=context.evidence_text,
        items=[
            KnowledgeChunkRead(
                id=item.id,
                source_id=item.source_id or "",
                title=item.title,
                content=item.content,
                relevance_score=item.relevance_score,
                metadata=item.metadata,
            )
            for item in context.items
        ],
    )


@router.post("/sources/{source_id}/embed")
async def embed_source(source_id: str, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    embedded_count = await KnowledgeEmbeddingService(db).embed_source(user_id=user.id, source_id=source_id)
    db.commit()
    return {"source_id": source_id, "embedded_chunks": embedded_count}


@router.get("/ai/verify")
async def verify_ai_path(user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    result: dict[str, object] = {
        "llm_provider": settings.llm_provider,
        "openai_model": settings.openai_model,
        "openai_json_model": settings.openai_json_model,
        "openai_embedding_model": settings.openai_embedding_model,
        "configured_embedding_dimension": settings.openai_embedding_dimension,
        "openai_key_configured": bool(settings.openai_api_key),
        "pgvector_column_available": KnowledgeRepository(db).pgvector_available(),
        "generation": "not_run",
        "structured_json": "not_run",
        "embedding": "not_run",
        "embedding_dimension_seen": None,
    }
    if not settings.openai_api_key:
        return result
    try:
        text_response = await ai_provider_service.llm.production().generate(
            instructions="Reply with exactly: CEASER OpenAI generation ready.",
            input_text="health check",
            max_output_tokens=32,
        )
        result["generation"] = "ok" if "ready" in text_response.lower() else "unexpected"
    except Exception as exc:
        result["generation"] = f"failed: {type(exc).__name__}"
    try:
        json_response = await ai_provider_service.llm.production().generate_json(
            instructions="Return JSON only.",
            input_text="Return status ready.",
            schema={"status": "ready"},
        )
        result["structured_json"] = "ok" if isinstance(json_response, dict) else "unexpected"
    except Exception as exc:
        result["structured_json"] = f"failed: {type(exc).__name__}"
    try:
        embedding = await ai_provider_service.embeddings.production().embed_query("CEASER semantic search health check")
        result["embedding"] = "ok" if embedding else "empty"
        result["embedding_dimension_seen"] = len(embedding)
    except Exception as exc:
        result["embedding"] = f"failed: {type(exc).__name__}"
    return result


@router.post("/orchestrate")
async def orchestrate(payload: ContextBuildRequest, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    request = RequestContext(
        user_id=user.id,
        message=payload.message,
        conversation_id=payload.conversation_id,
        project_id=payload.project_id,
        active_screen=payload.active_screen,
        interaction_mode=payload.interaction_mode,
    )
    result = await RequestOrchestrator(db).handle(request)
    db.commit()
    return result
