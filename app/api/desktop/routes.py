from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database.session import get_db
from app.core.security.dependencies import get_current_user
from app.models.user import User
from app.schemas.desktop import DesktopIntentRequest, DesktopIntentResponse
from app.schemas.desktop_cloud import DesktopCloudRequest, DesktopCloudResponse, DesktopDevicePayload, DesktopDeviceRead
from app.services.audit_service import AuditService
from app.services.desktop_auth_service import DesktopAuthService
from app.services.desktop_cloud_service import DesktopCloudService
from app.services.desktop_intent_classifier import DesktopIntentClassifier

router = APIRouter(prefix="/desktop", tags=["desktop"])


@router.post("/intent", response_model=DesktopIntentResponse)
def classify_desktop_intent(payload: DesktopIntentRequest, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    AuditService(db).record(
        user_id=user.id,
        action="desktop_command_received",
        resource_type="desktop",
        metadata={"command_length": len(payload.command), "command_preview": payload.command[:32]},
        commit=False,
    )
    result = DesktopIntentClassifier().classify(payload.command)
    AuditService(db).record(
        user_id=user.id,
        action="desktop_intent_classified",
        resource_type="desktop",
        metadata={"intent": result["intent"], "action": result["action"], "active_agent": result.get("active_agent")},
    )
    return result


@router.post("/devices", response_model=DesktopDeviceRead)
def register_desktop_device(payload: DesktopDevicePayload, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    device = DesktopAuthService(db).upsert_device(user, payload)
    db.commit()
    db.refresh(device)
    return _device_read(device)


@router.get("/devices", response_model=list[DesktopDeviceRead])
def list_desktop_devices(user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    return [_device_read(device) for device in DesktopAuthService(db).list_devices(user)]


@router.delete("/devices/{device_id}")
def revoke_desktop_device(device_id: str, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    DesktopAuthService(db).revoke(user, device_id=device_id)
    AuditService(db).record(user_id=user.id, action="desktop_device_revoked", resource_type="desktop", resource_id=device_id)
    return {"status": "ok"}


@router.post("/cloud/{action}", response_model=DesktopCloudResponse)
def desktop_cloud_action(action: str, payload: DesktopCloudRequest, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    try:
        result = DesktopCloudService(db).execute(user, action, payload)
    except HTTPException:
        raise
    AuditService(db).record(
        user_id=user.id,
        action=f"desktop_cloud_{action}",
        resource_type="desktop_cloud",
        resource_id=result.get("resource", {}).get("id") if isinstance(result.get("resource"), dict) else None,
        metadata={"resource_type": payload.resource_type, "has_query": bool(payload.query)},
    )
    return result


def _device_read(device) -> dict:
    return {
        "device_id": device.device_id,
        "device_name": device.device_name,
        "platform": device.platform,
        "app_version": device.app_version,
        "created_at": device.created_at,
        "last_seen_at": device.last_seen_at,
        "revoked_at": device.revoked_at,
        "status": "revoked" if device.revoked_at else "connected",
    }
