from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.auth.routes import router as auth_router
from app.api.automations.routes import router as automations_router
from app.api.agents.routes import router as agents_router
from app.api.capabilities.routes import router as capabilities_router
from app.api.ceaser.routes import router as ceaser_router
from app.api.conversations.routes import router as conversations_router
from app.api.documents.routes import router as documents_router
from app.api.desktop.routes import router as desktop_router
from app.api.drafts.routes import agent_router as agent_workbenches_router
from app.api.drafts.routes import router as drafts_router
from app.api.files.routes import router as files_router
from app.api.integrations.routes import router as integrations_router
from app.api.live.routes import router as live_router
from app.api.memories.routes import router as memories_router
from app.api.messages.routes import chat_router, router as messages_router
from app.api.projects.routes import router as projects_router
from app.api.research.routes import router as research_router
from app.api.voice.routes import router as voice_router
from app.api.workflows.routes import router as workflows_router
from app.core.config.settings import settings
from app.core.database.session import SessionLocal
from app.services.automations.automation_worker import automation_worker


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
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

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
    app.include_router(memories_router)
    app.include_router(projects_router)
    app.include_router(files_router)
    app.include_router(integrations_router)
    app.include_router(live_router)
    app.include_router(research_router)
    app.include_router(voice_router)
    app.include_router(workflows_router)

    @app.get("/health")
    def health() -> dict:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        return {"status": "healthy", "automation_worker": automation_worker.state.as_dict()}

    return app


app = create_app()
