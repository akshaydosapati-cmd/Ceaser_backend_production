from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.file import File
from app.core.config.settings import settings
from app.intelligence.ai.sync import generate_text_sync
from app.intelligence.knowledge.embedding_service import KnowledgeEmbeddingService
from app.intelligence.knowledge.repository import KnowledgeRepository
from app.repositories.file_repository import FileRepository
from app.services.documents import DocumentManager
from app.services.storage_service import StorageService


class FileService:
    def __init__(self, db: Session):
        self.files = FileRepository(db)
        self.db = db

    def list(self, user_id: str | None = None) -> list[File]:
        return self.files.list(user_id=user_id)

    def create(self, user_id: str, project_id: str | None, name: str, file_type: str, storage_path: str) -> File:
        file = self.files.create(user_id=user_id, project_id=project_id, name=name, file_type=file_type, storage_path=storage_path)
        self.db.commit()
        self.db.refresh(file)
        return file

    def get(self, file_id: str) -> File | None:
        return self.files.get(file_id)

    def update_project(self, file: File, project_id: str | None) -> File:
        updated = self.files.update_project(file, project_id)
        self.db.commit()
        self.db.refresh(updated)
        return updated

    def delete(self, file: File) -> None:
        self.files.delete(file)
        self.db.commit()

    def upload_and_process(self, *, user_id: str, project_id: str | None, filename: str, file_type: str, content: bytes, content_type: str) -> File:
        storage_path = StorageService().store(user_id=user_id, filename=filename, content=content, content_type=content_type)
        file = self.files.create(user_id=user_id, project_id=project_id, name=filename, file_type=file_type, storage_path=storage_path)
        extracted = DocumentManager().extract(StorageService().resolve(storage_path), file_type)
        file.extracted_content = extracted.content
        file.extraction_metadata = {"title": extracted.title, "pages": extracted.pages, **extracted.metadata}
        if extracted.content:
            source = KnowledgeRepository(self.db).ingest_text(
                user_id=user_id,
                title=filename,
                content=extracted.content,
                source_type="uploaded_file",
                project_id=project_id,
                metadata={"file_id": file.id, "file_type": file_type, "storage_path": storage_path, **file.extraction_metadata},
            )
            if settings.knowledge_auto_embed:
                try:
                    KnowledgeEmbeddingService(self.db).embed_source_sync(user_id=user_id, source_id=source.id)
                except Exception:
                    pass
        self.db.commit()
        self.db.refresh(file)
        return file

    def analyze(self, file: File, action: str, language: str | None = None, question: str | None = None) -> str:
        prompt = DocumentManager().build_prompt(action=action, file_name=file.name, content=file.extracted_content, language=language, question=question)
        instructions = (
            "You are CEASER document intelligence. Use the provided document content only when answering. "
            "Format the output for the requested action: summary, explanation, notes, MCQs, flashcards, or action items. "
            "Do not return generic template text."
        )
        try:
            return generate_text_sync(instructions=instructions, input_text=prompt)
        except Exception:
            return "AI service is temporarily unavailable. Please try again later."
