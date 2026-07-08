from __future__ import annotations

from sqlalchemy.orm import Session

from app.repositories.file_repository import FileRepository
from app.services.orchestrator.context_builder import ContextBuilder
from app.services.orchestrator.memory_retriever import MemoryRetriever
from app.services.orchestrator.user_context_resolver import UserContextResolver


class WorkflowContext:
    def __init__(self, db: Session):
        self.db = db
        self.user_context = UserContextResolver(db)
        self.memories = MemoryRetriever(db)
        self.context_builder = ContextBuilder(db)
        self.files = FileRepository(db)

    def build(self, *, user_id: str, message: str, selected_agents: list[dict], conversation_id: str | None = None, file_ids: list[str] | None = None) -> dict:
        user_context = self.user_context.resolve(user_id)
        memories = self.memories.retrieve_relevant_memories(user_id=user_id, query=message)
        context = self.context_builder.build_context(user_context=user_context, memories=memories, selected_agents=selected_agents, conversation_id=conversation_id)
        documents = []
        for file_id in (file_ids or [])[:3]:
            file = self.files.get(file_id)
            if file and file.user_id == user_id:
                documents.append({"id": file.id, "name": file.name, "file_type": file.file_type, "content": file.extracted_content[:20000], "metadata": file.extraction_metadata})
        context["message"] = message
        context["documents"] = documents
        context["workflow_handoffs"] = []
        return {"user_context": user_context, "memories": memories, "context": context}
