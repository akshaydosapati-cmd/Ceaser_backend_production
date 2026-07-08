from typing import Annotated

from fastapi import APIRouter, Depends, File as UploadFileField, Form, HTTPException, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.core.database.session import get_db
from app.core.security.access_control import require_file_access, require_project_access
from app.core.security.dependencies import get_current_user
from app.models.user import User
from app.schemas.file import DocumentActionRequest, DocumentActionResponse, FileContentRead, FileCreate, FileProjectUpdate, FileRead
from app.services.audit_service import AuditService
from app.services.file_service import FileService
from app.services.storage_service import StorageService

router = APIRouter(prefix="/files", tags=["files"])


@router.get("", response_model=list[FileRead])
def list_files(user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    return FileService(db).list(user_id=user.id)


@router.post("", response_model=FileRead, status_code=status.HTTP_201_CREATED)
def create_file(payload: FileCreate, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    file = FileService(db).create(user_id=user.id, project_id=payload.project_id, name=payload.name, file_type=payload.file_type, storage_path=payload.storage_path)
    AuditService(db).record(user_id=user.id, action="file_created", resource_type="file", resource_id=file.id, metadata={"file_type": file.file_type})
    return file


@router.post("/upload", response_model=FileRead, status_code=status.HTTP_201_CREATED)
async def upload_file(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    upload: UploadFile = UploadFileField(...),
    project_id: str | None = Form(default=None),
):
    content = await upload.read()
    file_type = _file_type(upload.filename or upload.content_type or "document")
    file = FileService(db).upload_and_process(
        user_id=user.id,
        project_id=project_id,
        filename=upload.filename or "upload",
        file_type=file_type,
        content=content,
        content_type=upload.content_type or "application/octet-stream",
    )
    metadata = {"file_type": file.file_type, "bytes": len(content), "pages": file.extraction_metadata.get("pages")}
    AuditService(db).record(user_id=user.id, action="document_uploaded", resource_type="file", resource_id=file.id, metadata=metadata)
    AuditService(db).record(user_id=user.id, action="document_read", resource_type="file", resource_id=file.id, metadata=file.extraction_metadata)
    if file.extraction_metadata.get("ocr"):
        AuditService(db).record(user_id=user.id, action="ocr_processed", resource_type="file", resource_id=file.id)
    return file


@router.get("/{file_id}", response_model=FileContentRead)
def get_file(file_id: str, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    file = require_file_access(db, user, file_id)
    AuditService(db).record(user_id=user.id, action="document_read", resource_type="file", resource_id=file.id)
    return file


@router.patch("/{file_id}/project", response_model=FileRead)
def update_file_project(file_id: str, payload: FileProjectUpdate, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    file = require_file_access(db, user, file_id)
    if payload.project_id:
        require_project_access(db, user, payload.project_id)
    updated = FileService(db).update_project(file, payload.project_id)
    AuditService(db).record(user_id=user.id, action="file_project_updated", resource_type="file", resource_id=file.id, metadata={"project_id": payload.project_id})
    return updated


@router.delete("/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_file(file_id: str, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    file = require_file_access(db, user, file_id)
    AuditService(db).record(user_id=user.id, action="file_deleted", resource_type="file", resource_id=file.id, metadata={"name": file.name, "file_type": file.file_type})
    FileService(db).delete(file)
    return None


@router.post("/{file_id}/analyze", response_model=DocumentActionResponse)
def analyze_file(file_id: str, payload: DocumentActionRequest, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    file = require_file_access(db, user, file_id)
    response = FileService(db).analyze(file, action=payload.action, language=payload.language, question=payload.question)
    AuditService(db).record(user_id=user.id, action="document_read", resource_type="file", resource_id=file.id, metadata={"action": payload.action})
    return {"file_id": file.id, "action": payload.action, "response": response}


@router.get("/{file_id}/download")
def download_file(file_id: str, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    file = require_file_access(db, user, file_id)
    content = StorageService().read_bytes(file.storage_path)
    return Response(content=content, media_type=_media_type(file.file_type), headers={"Content-Disposition": f'attachment; filename="{file.name}"'})


@router.get("/{file_id}/preview")
def preview_file(file_id: str, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    file = require_file_access(db, user, file_id)
    if file.file_type not in {"pdf", "png", "jpg", "jpeg", "txt"}:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Preview is not available for this file type")
    content = StorageService().read_bytes(file.storage_path)
    return Response(content=content, media_type=_media_type(file.file_type), headers={"Content-Disposition": f'inline; filename="{file.name}"'})


def _file_type(filename: str) -> str:
    suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else filename.lower()
    if suffix in {"pdf", "docx", "pptx", "xlsx", "txt", "png", "jpg", "jpeg"}:
        return suffix
    return "document"


def _media_type(file_type: str) -> str:
    return {
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "txt": "text/plain; charset=utf-8",
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
    }.get(file_type, "application/octet-stream")
