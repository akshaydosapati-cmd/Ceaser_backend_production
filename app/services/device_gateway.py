from __future__ import annotations

import asyncio
import time
from uuid import uuid4

from fastapi import WebSocket, WebSocketDisconnect

from app.agents.v2 import DeviceCapabilityResult
from app.core.config.settings import settings
from app.core.database.session import SessionLocal
from app.models.desktop import DesktopDevice
from app.services.desktop_auth_service import verify_desktop_access_token
from app.services.device_gateway_service import DeviceGatewayService
from app.services.bolt_repair_service import BoltRepairService
from app.services.browser_automation_coordinator import BrowserAutomationCoordinator
from app.services.social_publishing_service import SocialPublishingService


class DeviceGateway:
    async def handle(self, websocket: WebSocket) -> None:
        authorization = websocket.headers.get("authorization", "")
        if not authorization.lower().startswith("bearer "):
            await websocket.close(code=4401, reason="Missing device authorization")
            return
        payload = verify_desktop_access_token(authorization.split(" ", 1)[1])
        if not payload or not payload.get("sub") or not payload.get("device_id"):
            await websocket.close(code=4401, reason="Invalid device session")
            return
        user_id, device_id, session_id = payload["sub"], payload["device_id"], f"dgw_{uuid4().hex}"
        token_expires_at = int(payload.get("exp") or 0)
        with SessionLocal() as db:
            device = db.query(DesktopDevice).filter(DesktopDevice.user_id == user_id, DesktopDevice.device_id == device_id).first()
            if not device or device.revoked_at:
                await websocket.close(code=4403, reason="Device revoked")
                return
        await websocket.accept()
        capabilities: list[str] = []
        try:
            hello = await asyncio.wait_for(websocket.receive_json(), timeout=10)
            if hello.get("type") != "device.hello":
                await websocket.close(code=4400, reason="Device hello required")
                return
            capabilities = [str(item) for item in hello.get("capabilities", []) if isinstance(item, str)]
            with SessionLocal() as db:
                DeviceGatewayService(db).connect(user_id, device_id, session_id, capabilities)
            await websocket.send_json({"type": "gateway.ready", "device_id": device_id, "heartbeat_seconds": settings.device_gateway_heartbeat_seconds})
            while True:
                if token_expires_at and time.time() >= token_expires_at:
                    await websocket.close(code=4401, reason="Device session expired")
                    break
                if not await self._authorized(user_id, device_id, session_id):
                    await websocket.close(code=4403, reason="Device session revoked")
                    break
                await self._dispatch(websocket, user_id, device_id)
                try:
                    message = await asyncio.wait_for(websocket.receive_json(), timeout=max(0.1, settings.device_gateway_poll_ms / 1000))
                except asyncio.TimeoutError:
                    continue
                if message.get("type") == "device.heartbeat":
                    with SessionLocal() as db:
                        if not DeviceGatewayService(db).heartbeat(user_id, device_id, session_id):
                            await websocket.close(code=4403, reason="Device session revoked")
                            break
                    await websocket.send_json({"type": "gateway.heartbeat_ack"})
                elif message.get("type") == "device.capability.result":
                    result = DeviceCapabilityResult.model_validate(message.get("payload") or {})
                    with SessionLocal() as db:
                        command = DeviceGatewayService(db).complete(user_id, device_id, result)
                        BoltRepairService(db).handle(command)
                        BrowserAutomationCoordinator(db).handle(command)
                        SocialPublishingService(db).complete(command)
        except (WebSocketDisconnect, asyncio.TimeoutError):
            pass
        finally:
            with SessionLocal() as db:
                DeviceGatewayService(db).disconnect(user_id, device_id, session_id)

    async def _authorized(self, user_id: str, device_id: str, session_id: str) -> bool:
        with SessionLocal() as db:
            device = DeviceGatewayService(db).device(user_id, device_id)
            return bool(device and not device.revoked_at and device.gateway_session_id == session_id)

    async def _dispatch(self, websocket: WebSocket, user_id: str, device_id: str) -> None:
        with SessionLocal() as db:
            service = DeviceGatewayService(db)
            commands = service.pending(user_id, device_id)
            for command in commands:
                service.delivered(command)
                try:
                    await websocket.send_json({"type": "device.capability.request", "payload": command.request_json})
                except Exception:
                    service.requeue(command)
                    raise


device_gateway = DeviceGateway()
