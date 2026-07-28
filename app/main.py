from contextlib import asynccontextmanager
import logging
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI
from fastapi import HTTPException
from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.auth.routes import router as auth_router
from app.api.automations.routes import router as automations_router
from app.api.agents.routes import router as agents_router
from app.api.billing.routes import router as billing_router
from app.api.capabilities.routes import router as capabilities_router
from app.api.ceaser.routes import router as ceaser_router
from app.api.commercial.routes import router as commercial_router
from app.api.conversations.routes import router as conversations_router
from app.api.documents.routes import router as documents_router
from app.api.desktop.routes import router as desktop_router
from app.api.drafts.routes import agent_router as agent_workbenches_router
from app.api.drafts.routes import router as drafts_router
from app.api.files.routes import router as files_router
from app.api.integrations.routes import router as integrations_router
from app.api.knowledge.routes import router as knowledge_router
from app.api.live.routes import router as live_router
from app.api.memories.routes import router as memories_router
from app.api.messages.routes import chat_router, router as messages_router
from app.api.projects.routes import router as projects_router
from app.api.research.routes import router as research_router
from app.api.voice.routes import router as voice_router
from app.api.waitlist.routes import router as waitlist_router
from app.api.workflows.routes import router as workflows_router
from app.core.config.settings import settings
from app.core.database.session import SessionLocal
from app.intelligence.ai.errors import AIServiceUnavailableError
from app.services.automations.automation_worker import automation_worker


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    automation_worker.start()
    try:
        yield
    finally:
        await automation_worker.stop()


def create_app() -> FastAPI:
    app = FastAPI(title="CEASER Backend", version="0.1.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(dict.fromkeys([*settings.cors_origins, "ceaser-app://bundle"])),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def observability_middleware(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid4().hex
        request.state.request_id = request_id
        started = perf_counter()
        response = await call_next(request)
        elapsed_ms = round((perf_counter() - started) * 1000)
        response.headers["X-Request-Id"] = request_id
        response.headers["X-Process-Time-Ms"] = str(elapsed_ms)
        logger.info(
            "request_complete method=%s path=%s status=%s request_id=%s elapsed_ms=%s",
            request.method,
            request.url.path,
            response.status_code,
            request_id,
            elapsed_ms,
        )
        return response

    @app.exception_handler(AIServiceUnavailableError)
    async def ai_service_unavailable_handler(request: Request, exc: AIServiceUnavailableError) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": exc.public_message})

    app.include_router(auth_router)
    app.include_router(automations_router)
    app.include_router(agents_router)
    app.include_router(capabilities_router)
    app.include_router(conversations_router)
    app.include_router(documents_router)
    app.include_router(desktop_router)
    app.include_router(drafts_router)
    app.include_router(agent_workbenches_router)
    app.include_router(messages_router)
    app.include_router(chat_router)
    app.include_router(ceaser_router)
    app.include_router(billing_router)
    app.include_router(commercial_router)
    app.include_router(memories_router)
    app.include_router(projects_router)
    app.include_router(files_router)
    app.include_router(integrations_router)
    app.include_router(knowledge_router)
    app.include_router(live_router)
    app.include_router(research_router)
    app.include_router(voice_router)
    app.include_router(waitlist_router)
    app.include_router(workflows_router)

    @app.get("/")
    def root() -> dict:
        return {"service": "CEASER API", "status": "online", "version": app.version}

    @app.get("/health")
    @app.get("/health/live")
    def health() -> dict:
        return {"status": "healthy", "service": "ceaser-api", "version": app.version}

    @app.get("/health/ready")
    def readiness() -> dict:
        started = perf_counter()
        try:
            with SessionLocal() as db:
                db.execute(text("SELECT 1"))
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail={"status": "not_ready", "database": "unavailable", "reason": exc.__class__.__name__},
            ) from exc
        return {
            "status": "ready",
            "database": "ready",
            "auth": "configured" if settings.supabase_url and settings.supabase_anon_key else "not_configured",
            "ai": "configured" if settings.openai_api_key or settings.gemini_api_key else "not_configured",
            "voice": "configured" if settings.deepgram_api_key else "not_configured",
            "automation_worker": automation_worker.state.as_dict(),
            "latency_ms": round((perf_counter() - started) * 1000),
        }

    return app


app = create_app()
