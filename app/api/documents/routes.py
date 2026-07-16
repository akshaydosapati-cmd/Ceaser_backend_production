from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database.session import get_db
from app.core.security.dependencies import get_current_user
from app.models.file import File
from app.models.generated_document import GeneratedDocument
from app.models.user import User
from app.core.config.settings import settings
from app.intelligence.knowledge.embedding_service import KnowledgeEmbeddingService
from app.intelligence.knowledge.repository import KnowledgeRepository
from app.schemas.document_generation import AgentActivityRead, GenerateDocumentRequest, GenerateDocumentResponse, GeneratedDocumentRead, TemplateRead
from app.services.audit_service import AuditService
from app.services.document_generation import DocumentGenerator, TemplateManager
from app.services.document_generation.export_manager import ExportManager
from app.services.storage_service import StorageService

router = APIRouter(prefix="/documents", tags=["documents"])
agent_router = APIRouter(prefix="/agent-document-workbenches", tags=["agent-document-workbenches"])


@router.get("/templates", response_model=list[TemplateRead])
def list_templates(kind: str | None = None, agent_id: str | None = None):
    return TemplateManager().list(kind=kind, agent_id=agent_id)


@router.post("", response_model=GenerateDocumentResponse, status_code=status.HTTP_201_CREATED)
def generate_document(payload: GenerateDocumentRequest, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    try:
        result = DocumentGenerator().generate(prompt=payload.prompt, kind=payload.kind, template_id=payload.template_id, agent_id=payload.agent_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    storage_path = StorageService().store(user_id=user.id, filename=result.filename, content=result.bytes_data, content_type=result.content_type)
    file = File(user_id=user.id, project_id=None, name=result.filename, file_type=result.kind, storage_path=storage_path)
    file.extracted_content = result.content
    file.extraction_metadata = {
        "generated": True,
        "generated_by_agent": result.agent_id,
        "template_id": result.template.id,
        "template_name": result.template.name,
        "export_format": result.kind,
        "title": result.title,
        "pages": 1,
    }
    db.add(file)
    db.flush()
    generated = ExportManager(db).record_generated(file_id=file.id, user_id=user.id, agent_id=result.agent_id, template_id=result.template.id, export_format=result.kind, prompt=payload.prompt)
    source = KnowledgeRepository(db).ingest_text(
        user_id=user.id,
        title=result.filename,
        content=result.content,
        source_type="generated_document",
        project_id=file.project_id,
        metadata={
            "file_id": file.id,
            "generated_document_id": generated.id,
            "agent_id": result.agent_id,
            "template_id": result.template.id,
            "export_format": result.kind,
        },
    )
    if settings.knowledge_auto_embed:
        try:
            KnowledgeEmbeddingService(db).embed_source_sync(user_id=user.id, source_id=source.id)
        except Exception:
            pass
    AuditService(db).record(user_id=user.id, action="document_generated", resource_type="file", resource_id=file.id, metadata=file.extraction_metadata, commit=False)
    AuditService(db).record(user_id=user.id, action="template_used", resource_type="template", resource_id=result.template.id, commit=False)
    AuditService(db).record(user_id=user.id, action="agent_document_created", resource_type="agent", resource_id=result.agent_id, metadata={"file_id": file.id}, commit=False)
    db.commit()
    db.refresh(file)
    db.refresh(generated)
    return {"document": _document_read(generated, file), "file": _file_read(file), "preview": result.content}


@router.get("", response_model=list[GeneratedDocumentRead])
def list_generated_documents(user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)], agent_id: str | None = None):
    records = ExportManager(db).list_generated(user_id=user.id, agent_id=agent_id)
    return [_document_read(record, db.get(File, record.file_id)) for record in records]


@router.post("/{document_id}/export")
def export_document(document_id: str, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    record = db.get(GeneratedDocument, document_id)
    if not record or record.user_id != user.id:
        raise HTTPException(status_code=404, detail="Generated document not found.")
    AuditService(db).record(user_id=user.id, action="document_exported", resource_type="file", resource_id=record.file_id)
    return {"downloadUrl": f"/files/{record.file_id}/download", "file_id": record.file_id}


@agent_router.get("/{agent_id}", response_model=dict)
def get_agent_document_workbench(agent_id: str, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    return {
        "agent_id": agent_id,
        "templates": [item.model_dump() for item in TemplateManager().list(agent_id=agent_id)],
        "generated_documents": [_document_read(record, db.get(File, record.file_id)).model_dump() for record in ExportManager(db).list_generated(user_id=user.id, agent_id=agent_id)],
        "activity": [AgentActivityRead.model_validate(activity, from_attributes=True).model_dump() for activity in ExportManager(db).list_activity(user_id=user.id, agent_id=agent_id)],
    }


def _document_read(record: GeneratedDocument, file: File | None) -> GeneratedDocumentRead:
    return GeneratedDocumentRead(
        id=record.id,
        file_id=record.file_id,
        user_id=record.user_id,
        agent_id=record.agent_id,
        template_id=record.template_id,
        generated_by=record.generated_by,
        export_format=record.export_format,
        version=record.version,
        source_prompt=record.source_prompt,
        created_at=record.created_at,
        file_name=file.name if file else None,
    )


def _file_read(file: File) -> dict:
    return {
        "id": file.id,
        "user_id": file.user_id,
        "project_id": file.project_id,
        "name": file.name,
        "file_type": file.file_type,
        "storage_path": file.storage_path,
        "extraction_metadata": file.extraction_metadata,
        "created_at": file.created_at.isoformat(),
    }
