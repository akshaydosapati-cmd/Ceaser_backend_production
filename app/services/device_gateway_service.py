from __future__ import annotations

from datetime import timedelta, timezone

from sqlalchemy.orm import Session

from app.agents.v2 import DeviceCapabilityRequest, DeviceCapabilityResult
from app.core.config.settings import settings
from app.execution.placement import DeviceAvailability
from app.models.desktop import DesktopCommand, DesktopDevice
from app.models.mixins import utc_now
from app.models.user import User


TERMINAL_COMMANDS = ("COMPLETED", "FAILED", "TIMEOUT", "CANCELLED")


def _aware(value):
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


class DeviceGatewayService:
    def __init__(self, db: Session):
        self.db = db

    def device(self, user_id: str, device_id: str) -> DesktopDevice | None:
        return self.db.query(DesktopDevice).filter(DesktopDevice.user_id == user_id, DesktopDevice.device_id == device_id).first()

    def availability(self, user_id: str, capability: str, *, preferred_device_id: str | None = None) -> list[DeviceAvailability]:
        devices = self.db.query(DesktopDevice).filter(DesktopDevice.user_id == user_id).all()
        return [
            DeviceAvailability(
                device_id=device.device_id,
                user_id=device.user_id,
                connected=self.is_online(device),
                authenticated=not bool(device.revoked_at),
                authorized=not bool(device.revoked_at),
                advertised_capabilities=frozenset(device.capabilities_json or []),
                preferred=device.device_id == preferred_device_id,
            )
            for device in devices
            if not device.revoked_at and (not device.capabilities_json or capability in device.capabilities_json)
        ]

    def connect(self, user_id: str, device_id: str, session_id: str, capabilities: list[str]) -> DesktopDevice:
        device = self.device(user_id, device_id)
        if not device or device.revoked_at:
            raise PermissionError("Device is missing or revoked")
        now = utc_now()
        device.gateway_session_id = session_id
        device.gateway_connected_at = now
        device.gateway_last_heartbeat_at = now
        device.gateway_disconnected_at = None
        device.capabilities_json = sorted(set(capabilities))[:500]
        device.last_seen_at = now
        self.db.query(DesktopCommand).filter(
            DesktopCommand.user_id == user_id,
            DesktopCommand.device_id == device_id,
            DesktopCommand.status.in_(("DELIVERED", "WAITING_FOR_DEVICE")),
            DesktopCommand.expires_at >= now,
        ).update({"status": "QUEUED", "updated_at": now}, synchronize_session=False)
        self.db.commit()
        return device

    def heartbeat(self, user_id: str, device_id: str, session_id: str) -> bool:
        device = self.device(user_id, device_id)
        if not device or device.revoked_at or device.gateway_session_id != session_id:
            return False
        now = utc_now()
        device.gateway_last_heartbeat_at = now
        device.last_seen_at = now
        self.db.commit()
        return True

    def disconnect(self, user_id: str, device_id: str, session_id: str) -> None:
        device = self.device(user_id, device_id)
        if device and device.gateway_session_id == session_id:
            now = utc_now()
            device.gateway_session_id = None
            device.gateway_disconnected_at = now
            self.db.query(DesktopCommand).filter(
                DesktopCommand.user_id == user_id,
                DesktopCommand.device_id == device_id,
                DesktopCommand.status == "DELIVERED",
                DesktopCommand.expires_at >= now,
            ).update({"status": "WAITING_FOR_DEVICE", "updated_at": now}, synchronize_session=False)
            self.db.commit()

    @staticmethod
    def is_online(device: DesktopDevice) -> bool:
        heartbeat = _aware(device.gateway_last_heartbeat_at)
        return bool(
            not device.revoked_at and device.gateway_session_id and heartbeat
            and heartbeat >= utc_now() - timedelta(seconds=settings.device_gateway_offline_seconds)
        )

    def submit(self, user: User, request: DeviceCapabilityRequest) -> DesktopCommand:
        if request.authorization.get("user_id") not in (None, user.id):
            raise PermissionError("Command owner mismatch")
        device = self.device(user.id, request.device_id)
        if not device:
            raise LookupError("Device not found")
        if device.revoked_at:
            raise PermissionError("Device is revoked")
        if not self.is_online(device):
            raise ConnectionError("Device is offline")
        if device.capabilities_json and request.capability not in device.capabilities_json:
            raise LookupError("Device capability unavailable")
        existing = self.db.query(DesktopCommand).filter(DesktopCommand.user_id == user.id, DesktopCommand.request_id == request.request_id).first()
        if existing:
            return existing
        now = utc_now()
        safe_request = request.model_copy(update={"authorization": {"user_id": user.id}})
        command = DesktopCommand(
            user_id=user.id, device_id=request.device_id, request_id=request.request_id, task_id=request.task_id,
            agent_id=request.agent_id, capability=request.capability, request_json=safe_request.model_dump(mode="json"),
            status="QUEUED", expires_at=now + timedelta(seconds=request.timeout_seconds), updated_at=now,
        )
        self.db.add(command)
        self.db.commit()
        self.db.refresh(command)
        return command

    def pending(self, user_id: str, device_id: str) -> list[DesktopCommand]:
        now = utc_now()
        expired = self.db.query(DesktopCommand).filter(
            DesktopCommand.user_id == user_id,
            DesktopCommand.device_id == device_id,
            DesktopCommand.status.in_(("QUEUED", "WAITING_FOR_DEVICE")),
            DesktopCommand.expires_at < now,
        ).all()
        for command in expired:
            command.status = "TIMEOUT"
            command.safe_error = "Device command timed out."
            command.completed_at = now
            command.updated_at = now
        if expired:
            self.db.commit()
        return self.db.query(DesktopCommand).filter(
            DesktopCommand.user_id == user_id,
            DesktopCommand.device_id == device_id,
            DesktopCommand.status == "QUEUED",
            DesktopCommand.expires_at >= now,
        ).order_by(DesktopCommand.created_at.asc()).all()

    def delivered(self, command: DesktopCommand) -> DesktopCommand:
        if command.status == "QUEUED":
            now = utc_now()
            command.status = "DELIVERED"
            command.delivered_at = now
            command.updated_at = now
            self.db.commit()
        return command

    def complete(self, user_id: str, device_id: str, result: DeviceCapabilityResult) -> DesktopCommand:
        command = self.db.query(DesktopCommand).filter(
            DesktopCommand.user_id == user_id,
            DesktopCommand.device_id == device_id,
            DesktopCommand.request_id == result.request_id,
        ).first()
        if not command:
            raise LookupError("Device command not found")
        if command.status in TERMINAL_COMMANDS:
            return command
        now = utc_now()
        command.status = result.status.upper()
        command.result_json = result.model_dump(mode="json")
        command.safe_error = self._safe_error(result.error)
        command.completed_at = now
        command.updated_at = now
        self.db.commit()
        return command

    def owned_command(self, user: User, request_id: str) -> DesktopCommand | None:
        return self.db.query(DesktopCommand).filter(DesktopCommand.user_id == user.id, DesktopCommand.request_id == request_id).first()

    @staticmethod
    def _safe_error(error: dict | None) -> str | None:
        if not error:
            return None
        return str(error.get("message") or error.get("code") or "Device command failed.")[:500]