from __future__ import annotations

import hashlib
import hmac
import re
from urllib.parse import urlencode
from datetime import timedelta
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.config.settings import settings
from app.models.desktop import DesktopCloudResource
from app.models.mixins import utc_now
from app.models.user import User
from app.schemas.desktop_cloud import DesktopCloudRequest
from app.services.storage_service import StorageService


ALLOWED_ACTIONS = {"list", "search", "latest", "read", "create", "update", "delete", "restore", "upload", "download"}
ALLOWED_MIME_PREFIXES = ("text/", "image/", "application/pdf", "application/json")
ALLOWED_MIME_TYPES = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}
MAX_UPLOAD_BYTES = 25 * 1024 * 1024


class DesktopCloudService:
    def __init__(self, db: Session):
        self.db = db

    def execute(self, user: User, action: str, payload: DesktopCloudRequest) -> dict[str, Any]:
        if action not in ALLOWED_ACTIONS:
            raise HTTPException(status_code=404, detail="Unsupported desktop cloud action")
        handler = getattr(self, f"_{action}")
        return handler(user, payload)

    def _list(self, user: User, payload: DesktopCloudRequest) -> dict[str, Any]:
        query = self._active_query(user)
        if payload.resource_type:
            query = query.filter(DesktopCloudResource.resource_type == payload.resource_type)
        items = query.order_by(DesktopCloudResource.updated_at.desc().nullslast(), DesktopCloudResource.created_at.desc()).limit(20).all()
        return self._response("list", f"Found {len(items)} CEASER cloud resources.", items=items)

    def _search(self, user: User, payload: DesktopCloudRequest) -> dict[str, Any]:
        term = self._clean_query(payload.query or payload.command or "")
        if not term:
            raise HTTPException(status_code=422, detail="Search query is required")
        pattern = f"%{term.lower()}%"
        items = (
            self._active_query(user)
            .filter(or_(DesktopCloudResource.name.ilike(pattern), DesktopCloudResource.resource_type.ilike(pattern)))
            .order_by(DesktopCloudResource.updated_at.desc().nullslast(), DesktopCloudResource.created_at.desc())
            .limit(20)
            .all()
        )
        return self._response("search", f"Found {len(items)} matching resources.", items=items)

    def _latest(self, user: User, payload: DesktopCloudRequest) -> dict[str, Any]:
        query = self._active_query(user)
        resource_type = payload.resource_type if payload.resource_type not in (None, "resource") else None
        if resource_type:
            query = query.filter(DesktopCloudResource.resource_type == resource_type)
        resource = query.order_by(DesktopCloudResource.updated_at.desc().nullslast(), DesktopCloudResource.created_at.desc()).first()
        if not resource:
            raise HTTPException(status_code=404, detail="No matching CEASER cloud resource found")
        return self._response("latest", f"Latest resource: {resource.name}", resource=resource, items=[resource])

    def _read(self, user: User, payload: DesktopCloudRequest) -> dict[str, Any]:
        resource = self._resolve_resource(user, payload)
        return self._response("read", f"Opened {resource.name}.", resource=resource, items=[resource])

    def _create(self, user: User, payload: DesktopCloudRequest) -> dict[str, Any]:
        name = self._safe_name(payload.name or payload.query or "Untitled resource")
        resource = DesktopCloudResource(
            user_id=user.id,
            project_id=payload.project_id,
            name=name,
            resource_type=payload.resource_type or "document",
            mime_type=payload.mime_type,
            storage_path=self._safe_storage_path(payload.storage_path),
            version=1,
            status="active",
            updated_at=utc_now(),
            metadata_json=payload.metadata or {},
            content_encrypted=payload.content,
        )
        self.db.add(resource)
        self.db.commit()
        self.db.refresh(resource)
        return self._response("create", f"Created {resource.name}.", resource=resource, items=[resource])

    def _update(self, user: User, payload: DesktopCloudRequest) -> dict[str, Any]:
        resource = self._resolve_resource(user, payload)
        if payload.name:
            resource.name = self._safe_name(payload.name)
        if payload.content is not None:
            resource.content_encrypted = payload.content
        if payload.metadata:
            resource.metadata_json = {**(resource.metadata_json or {}), **payload.metadata}
        if payload.storage_path:
            resource.storage_path = self._safe_storage_path(payload.storage_path)
        resource.version += 1
        resource.updated_at = utc_now()
        self.db.commit()
        self.db.refresh(resource)
        return self._response("update", f"Updated {resource.name} to version {resource.version}.", resource=resource, items=[resource])

    def _delete(self, user: User, payload: DesktopCloudRequest) -> dict[str, Any]:
        resource = self._resolve_resource(user, payload)
        resource.status = "deleted"
        resource.deleted_at = utc_now()
        resource.updated_at = utc_now()
        self.db.commit()
        self.db.refresh(resource)
        return self._response("delete", f"Deleted {resource.name}. You can restore it later.", resource=resource, items=[resource])

    def _restore(self, user: User, payload: DesktopCloudRequest) -> dict[str, Any]:
        resource = self._resolve_resource(user, payload, include_deleted=True)
        resource.status = "active"
        resource.deleted_at = None
        resource.updated_at = utc_now()
        self.db.commit()
        self.db.refresh(resource)
        return self._response("restore", f"Restored {resource.name}.", resource=resource, items=[resource])

    def _upload(self, user: User, payload: DesktopCloudRequest) -> dict[str, Any]:
        self._validate_upload(payload)
        name = self._safe_name(payload.name or payload.query or "Desktop upload")
        storage_path = self._safe_storage_path(payload.storage_path or f"desktop/{user.id}/{name}")
        resource = DesktopCloudResource(
            user_id=user.id,
            project_id=payload.project_id,
            name=name,
            resource_type=payload.resource_type or "file",
            mime_type=payload.mime_type,
            storage_path=storage_path,
            version=1,
            status="pending_upload",
            updated_at=utc_now(),
            metadata_json={**(payload.metadata or {}), "size_bytes": payload.size_bytes or 0},
        )
        self.db.add(resource)
        self.db.commit()
        self.db.refresh(resource)
        return self._response("upload", f"Prepared secure upload for {resource.name}.", resource=resource, items=[resource], signed_upload_url=self._signed_url("upload", resource))

    def _download(self, user: User, payload: DesktopCloudRequest) -> dict[str, Any]:
        resource = self._resolve_resource(user, payload)
        if not resource.storage_path:
            raise HTTPException(status_code=404, detail="The requested cloud resource has no stored file")
        return self._response("download", f"Prepared secure download for {resource.name}.", resource=resource, items=[resource], signed_download_url=self._signed_url("download", resource))

    def complete_signed_upload(self, resource_id: str, purpose: str, expires: int, signature: str, content: bytes) -> DesktopCloudResource:
        resource = self._verify_signed_resource(resource_id, purpose, expires, signature)
        if purpose != "upload":
            raise HTTPException(status_code=400, detail="Invalid signed upload purpose")
        metadata = resource.metadata_json or {}
        expected_size = int(metadata.get("size_bytes") or 0)
        if len(content) > MAX_UPLOAD_BYTES or (expected_size and len(content) > expected_size):
            raise HTTPException(status_code=413, detail="Uploaded file is larger than expected")
        mime_type = resource.mime_type or "application/octet-stream"
        if not self._mime_allowed(mime_type):
            raise HTTPException(status_code=415, detail="File type is not supported")
        checksum = hashlib.sha256(content).hexdigest()
        storage_path = StorageService().store(
            user_id=resource.user_id,
            filename=resource.name,
            content=content,
            content_type=mime_type,
        )
        resource.storage_path = storage_path
        resource.status = "active"
        resource.updated_at = utc_now()
        resource.metadata_json = {**metadata, "size_bytes": len(content), "sha256": checksum}
        self.db.commit()
        self.db.refresh(resource)
        return resource

    def read_signed_download(self, resource_id: str, purpose: str, expires: int, signature: str) -> tuple[DesktopCloudResource, bytes]:
        resource = self._verify_signed_resource(resource_id, purpose, expires, signature)
        if purpose != "download":
            raise HTTPException(status_code=400, detail="Invalid signed download purpose")
        if resource.deleted_at or resource.status == "deleted" or not resource.storage_path:
            raise HTTPException(status_code=404, detail="CEASER cloud resource file not found")
        try:
            content = StorageService().read_bytes(resource.storage_path)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="CEASER cloud resource file is missing") from exc
        return resource, content

    def _active_query(self, user: User):
        return self.db.query(DesktopCloudResource).filter(DesktopCloudResource.user_id == user.id, DesktopCloudResource.deleted_at.is_(None))

    def _resolve_resource(self, user: User, payload: DesktopCloudRequest, *, include_deleted: bool = False) -> DesktopCloudResource:
        query = self.db.query(DesktopCloudResource).filter(DesktopCloudResource.user_id == user.id)
        if not include_deleted:
            query = query.filter(DesktopCloudResource.deleted_at.is_(None))
        if payload.resource_id:
            resource = query.filter(DesktopCloudResource.id == payload.resource_id).first()
        else:
            term = self._clean_query(payload.query or payload.name or payload.command or "")
            resource = query.filter(DesktopCloudResource.name.ilike(f"%{term}%")).order_by(DesktopCloudResource.updated_at.desc().nullslast(), DesktopCloudResource.created_at.desc()).first() if term else None
            if not resource and ("latest" in str(payload.command or "").lower() or not term):
                resource = query.order_by(DesktopCloudResource.updated_at.desc().nullslast(), DesktopCloudResource.created_at.desc()).first()
        if not resource:
            raise HTTPException(status_code=404, detail="CEASER cloud resource not found")
        return resource

    def _validate_upload(self, payload: DesktopCloudRequest) -> None:
        if payload.size_bytes is not None and payload.size_bytes > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="File is too large for desktop upload")
        mime = payload.mime_type or "application/octet-stream"
        if not self._mime_allowed(mime):
            raise HTTPException(status_code=415, detail="File type is not supported")
        self._safe_storage_path(payload.storage_path or "pending")

    def _mime_allowed(self, mime: str) -> bool:
        return mime.startswith(ALLOWED_MIME_PREFIXES) or mime in ALLOWED_MIME_TYPES

    def _safe_storage_path(self, value: str | None) -> str | None:
        if not value:
            return None
        cleaned = str(value).replace("\\", "/").strip()
        if ".." in cleaned.split("/") or cleaned.startswith("/") or re.match(r"^[a-zA-Z]:", cleaned):
            raise HTTPException(status_code=400, detail="Invalid storage path")
        return cleaned[:1000]

    def _safe_name(self, value: str) -> str:
        cleaned = re.sub(r"[\r\n\t/\\]+", " ", str(value or "Untitled")).strip()
        return cleaned[:255] or "Untitled"

    def _clean_query(self, value: str) -> str:
        text = re.sub(r"\b(search|find|read|open|show|latest|my|ceaser|files?|documents?|reports?|for|about)\b", " ", str(value or ""), flags=re.IGNORECASE)
        return re.sub(r"\s+", " ", text).strip()[:255]

    def _signed_url(self, purpose: str, resource: DesktopCloudResource) -> str:
        expires = int((utc_now() + timedelta(minutes=10)).timestamp())
        signature = self._signed_signature(purpose, resource.user_id, resource.id, expires)
        return f"/desktop/cloud/signed/{resource.id}?{urlencode({'purpose': purpose, 'expires': expires, 'signature': signature})}"

    def _signed_signature(self, purpose: str, user_id: str, resource_id: str, expires: int) -> str:
        secret = (settings.jwt_secret or settings.encryption_master_key or "").encode("utf-8")
        if not secret:
            raise HTTPException(status_code=503, detail="Desktop cloud signing secret is not configured")
        body = f"{purpose}:{user_id}:{resource_id}:{expires}"
        return hmac.new(secret, body.encode("utf-8"), hashlib.sha256).hexdigest()

    def _verify_signed_resource(self, resource_id: str, purpose: str, expires: int, signature: str) -> DesktopCloudResource:
        if expires < int(utc_now().timestamp()):
            raise HTTPException(status_code=401, detail="Signed desktop cloud URL expired")
        resource = self.db.get(DesktopCloudResource, resource_id)
        if not resource:
            raise HTTPException(status_code=404, detail="CEASER cloud resource not found")
        expected = self._signed_signature(purpose, resource.user_id, resource.id, expires)
        if not hmac.compare_digest(expected, signature or ""):
            raise HTTPException(status_code=401, detail="Invalid signed desktop cloud URL")
        return resource

    def _response(self, action: str, message: str, *, items: list[DesktopCloudResource] | None = None, resource: DesktopCloudResource | None = None, signed_upload_url: str | None = None, signed_download_url: str | None = None) -> dict[str, Any]:
        serialized_items = [self._serialize(item) for item in (items or [])]
        return {
            "status": "completed",
            "action": action,
            "verified": True,
            "message": message,
            "items": serialized_items,
            "resource": self._serialize(resource) if resource else None,
            "signed_upload_url": signed_upload_url,
            "signed_download_url": signed_download_url,
        }

    def _serialize(self, resource: DesktopCloudResource | None) -> dict[str, Any] | None:
        if not resource:
            return None
        return {
            "id": resource.id,
            "name": resource.name,
            "resource_type": resource.resource_type,
            "mime_type": resource.mime_type,
            "storage_path": resource.storage_path,
            "version": resource.version,
            "status": resource.status,
            "created_at": resource.created_at.isoformat() if resource.created_at else None,
            "updated_at": resource.updated_at.isoformat() if resource.updated_at else None,
            "deleted_at": resource.deleted_at.isoformat() if resource.deleted_at else None,
            "metadata": resource.metadata_json or {},
            "content": resource.content_encrypted,
        }
