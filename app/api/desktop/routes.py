from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, WebSocket
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
from app.agents.v2 import DeviceCapabilityRequest
from app.services.device_gateway import device_gateway
from app.services.device_gateway_service import DeviceGatewayService

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
async def revoke_desktop_device(device_id: str, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    DesktopAuthService(db).revoke(user, device_id=device_id)
    AuditService(db).record(user_id=user.id, action="desktop_device_revoked", resource_type="desktop", resource_id=device_id)
    return {"status": "ok"}


@router.websocket("/gateway")
async def desktop_gateway(websocket: WebSocket):
    await device_gateway.handle(websocket)


@router.post("/commands", status_code=202)
async def submit_desktop_command(
    payload: DeviceCapabilityRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    wait_seconds: float = Query(default=0, ge=0, le=30),
):
    try:
        command = DeviceGatewayService(db).submit(user, payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    deadline = asyncio.get_running_loop().time() + wait_seconds
    while wait_seconds and asyncio.get_running_loop().time() < deadline and command.status not in ("COMPLETED", "FAILED", "TIMEOUT", "CANCELLED"):
        await asyncio.sleep(0.1)
        db.expire_all()
        command = DeviceGatewayService(db).owned_command(user, payload.request_id)
    return _command_read(command)


@router.get("/commands/{request_id}")
def get_desktop_command(request_id: str, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    command = DeviceGatewayService(db).owned_command(user, request_id)
    if not command:
        raise HTTPException(status_code=404, detail="Desktop command not found")
    return _command_read(command)


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


@router.put("/cloud/signed/{resource_id}")
async def upload_signed_desktop_resource(
    resource_id: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    purpose: str = Query(...),
    expires: int = Query(...),
    signature: str = Query(...),
):
    content = await request.body()
    resource = DesktopCloudService(db).complete_signed_upload(resource_id, purpose, expires, signature, content)
    AuditService(db).record(
        user_id=resource.user_id,
        action="desktop_cloud_upload_completed",
        resource_type="desktop_cloud",
        resource_id=resource.id,
        metadata={"bytes": len(content), "mime_type": resource.mime_type},
    )
    return {"status": "completed", "verified": True, "resource": DesktopCloudService(db)._serialize(resource)}


@router.get("/cloud/signed/{resource_id}")
def download_signed_desktop_resource(
    resource_id: str,
    db: Annotated[Session, Depends(get_db)],
    purpose: str = Query(...),
    expires: int = Query(...),
    signature: str = Query(...),
):
    resource, content = DesktopCloudService(db).read_signed_download(resource_id, purpose, expires, signature)
    AuditService(db).record(
        user_id=resource.user_id,
        action="desktop_cloud_download_completed",
        resource_type="desktop_cloud",
        resource_id=resource.id,
        metadata={"bytes": len(content), "mime_type": resource.mime_type},
    )
    safe_name = str(resource.name or "download").replace('"', "")
    return Response(
        content=content,
        media_type=resource.mime_type or "application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_name}"',
            "X-CEASER-Resource-Id": resource.id,
            "X-CEASER-Resource-Version": str(resource.version),
        },
    )


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
        "gateway_status": "online" if DeviceGatewayService.is_online(device) else "offline",
        "gateway_last_heartbeat_at": device.gateway_last_heartbeat_at,
        "capabilities": device.capabilities_json or [],
    }


def _command_read(command) -> dict:
    return {
        "id": command.id, "request_id": command.request_id, "task_id": command.task_id,
        "device_id": command.device_id, "capability": command.capability, "status": command.status,
        "result": command.result_json, "error": command.safe_error, "created_at": command.created_at,
        "delivered_at": command.delivered_at, "completed_at": command.completed_at, "expires_at": command.expires_at,
    }
