from __future__ import annotations

import asyncio
import json
import uuid
from time import perf_counter

from sqlalchemy import text

from app.core.database.session import SessionLocal
from app.intelligence.knowledge.repository import KnowledgeRepository
from app.models.file import File
from app.models.user import User
from app.services.orchestrator import CeaserOrchestrator


PROMPT = "Summarize the uploaded document."
SAMPLE_TEXT = """CEASER is a personal AI operating system built to combine projects, memory, files, and connected tools into one intelligent workflow layer.

For document intelligence, the most important behavior is reuse. A file should be extracted once, chunked once, and then summarized from stored chunks rather than reparsed on every request.

Fast file summarization depends on narrowing retrieval to the selected file, limiting the number of chunks, and sending only the most relevant evidence into the model prompt.

When this path is implemented well, the assistant should respond quickly, preserve document fidelity, and avoid dragging in unrelated memory, project, or web context.
"""


async def _stream_once(orchestrator: CeaserOrchestrator, prepared: dict, request_id: str) -> tuple[str, dict]:
    trace: dict[str, object] = {"request_id": request_id}
    chunks: list[str] = []
    started = perf_counter()
    first_token_seen = False
    async for chunk in orchestrator.response_pipeline.stream(prepared["effective_message"], prepared["context"], trace=trace):
        if not first_token_seen:
            trace["endpoint_ttft_ms"] = round((perf_counter() - started) * 1000, 2)
            first_token_seen = True
        chunks.append(chunk)
    response_text = "".join(chunks).strip()
    trace["output_tokens"] = max(1, round(len(response_text) / 4)) if response_text else 0
    trace["total_time_ms"] = round((perf_counter() - started) * 1000, 2)
    prepared["stream_trace"] = trace
    return response_text, trace


def main() -> int:
    db = SessionLocal()
    created_user_id = None
    created_file_id = None
    created_source_id = None
    try:
        user = User(email=f"ceaser-file-rag-{uuid.uuid4().hex[:10]}@local.test")
        db.add(user)
        db.flush()
        created_user_id = user.id

        file = File(
            user_id=user.id,
            project_id=None,
            name="file-rag-smoke.txt",
            file_type="txt",
            storage_path="smoke://file-rag-smoke.txt",
        )
        file.extracted_content = SAMPLE_TEXT
        file.extraction_metadata = {"title": "File RAG Smoke Test", "pages": 1}
        db.add(file)
        db.flush()
        created_file_id = file.id

        source = KnowledgeRepository(db).ingest_text(
            user_id=user.id,
            title=file.name,
            content=SAMPLE_TEXT,
            source_type="uploaded_file",
            metadata={"file_id": file.id, "file_type": file.file_type, **file.extraction_metadata},
        )
        created_source_id = source.id
        db.commit()

        results: list[dict] = []
        orchestrator = CeaserOrchestrator(db)
        for run in range(1, 4):
            prepared = orchestrator.prepare_stream_request(
                user_id=user.id,
                message=PROMPT,
                conversation_id=None,
                file_ids=[file.id],
            )
            response_text, trace = asyncio.run(_stream_once(orchestrator, prepared, f"file-rag-run-{run}"))
            final_payload = orchestrator.finalize_stream_response(prepared, response_text)
            context = final_payload.get("context_summary", {})
            results.append(
                {
                    "run": run,
                    "retrieval_ms": context.get("retrieval_time_ms"),
                    "endpoint_ttft_ms": context.get("endpoint_ttft_ms"),
                    "total_ms": context.get("total_time_ms"),
                    "prompt_tokens": context.get("prompt_tokens"),
                    "selected_chunks": context.get("selected_chunks"),
                    "cache_hit": context.get("cache_hit"),
                    "words": len(response_text.split()),
                    "provider": context.get("provider"),
                    "model": context.get("model"),
                    "fallback_used": context.get("fallback_used"),
                    "file_lookup_ms": context.get("file_lookup_ms"),
                    "chunk_load_ms": context.get("chunk_load_ms"),
                    "vector_search_ms": context.get("vector_search_ms"),
                    "keyword_search_ms": context.get("keyword_search_ms"),
                    "rerank_ms": context.get("rerank_ms"),
                    "context_build_ms": context.get("context_build_ms"),
                    "provider_connect_ms": context.get("provider_connect_ms"),
                    "upstream_ttft_ms": context.get("upstream_ttft_ms"),
                    "response": response_text,
                }
            )
            db.commit()

        print(json.dumps(results, indent=2))
        return 0
    finally:
        db.rollback()
        if created_source_id:
            db.execute(text("DELETE FROM knowledge_retrieval_logs WHERE user_id = :user_id"), {"user_id": created_user_id})
            db.execute(text("DELETE FROM context_runs WHERE user_id = :user_id"), {"user_id": created_user_id})
            db.execute(text("DELETE FROM knowledge_chunks WHERE source_id = :source_id"), {"source_id": created_source_id})
            db.execute(text("DELETE FROM knowledge_sources WHERE id = :source_id"), {"source_id": created_source_id})
        if created_file_id:
            db.execute(text("DELETE FROM files WHERE id = :file_id"), {"file_id": created_file_id})
        if created_user_id:
            db.execute(text("DELETE FROM users WHERE id = :user_id"), {"user_id": created_user_id})
        db.commit()
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
