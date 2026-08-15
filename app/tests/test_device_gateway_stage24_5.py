import asyncio
from datetime import timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.websockets import WebSocketDisconnect

from app.agents.v2 import DeviceCapabilityRequest, DeviceCapabilityResult, ExecutionTarget
from app.core.config.settings import settings
from app.core.database.base import Base
from app.execution.placement import ExecutionDecision, ExecutionRequest
from app.models.desktop import DesktopCommand, DesktopDevice
from app.models.mixins import utc_now
from app.models.user import User
from app.services.device_gateway_service import DeviceGatewayService
from app.services.device_gateway import device_gateway
from app.services.persistent_device_executor import PersistentDeviceExecutor


engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)


@pytest.fixture(autouse=True)
def database(monkeypatch):
    Base.metadata.drop_all(engine); Base.metadata.create_all(engine)
    monkeypatch.setattr(settings, "device_gateway_offline_seconds", 60)


def seed(db, email="user@example.com", device_id="device-1"):
    user = User(email=email); db.add(user); db.flush()
    device = DesktopDevice(user_id=user.id, device_id=device_id, device_name="Laptop")
    db.add(device); db.commit(); db.refresh(user); db.refresh(device)
    return user, device


def contract(user, device_id="device-1", request_id="request-1", capability="desktop.open_application"):
    return DeviceCapabilityRequest(
        request_id=request_id, task_id="task-1", agent_id="friday", device_id=device_id,
        capability=capability, arguments={"name": "Chrome"}, authorization={"user_id": user.id}, timeout_seconds=30,
    )


def test_authenticated_connection_and_realtime_status():
    with Session() as db:
        user, device = seed(db)
        service = DeviceGatewayService(db)
        service.connect(user.id, device.device_id, "session-1", ["desktop.open_application"])
        assert service.is_online(device) and device.capabilities_json == ["desktop.open_application"]
        assert service.heartbeat(user.id, device.device_id, "session-1")
        service.disconnect(user.id, device.device_id, "session-1")
        assert not service.is_online(device)


def test_wrong_session_cannot_heartbeat_or_disconnect_active_session():
    with Session() as db:
        user, device = seed(db)
        service = DeviceGatewayService(db); service.connect(user.id, device.device_id, "active", [])
        assert service.heartbeat(user.id, device.device_id, "wrong") is False
        service.disconnect(user.id, device.device_id, "wrong")
        assert device.gateway_session_id == "active"


def test_command_correlation_delivery_and_result():
    with Session() as db:
        user, device = seed(db)
        service = DeviceGatewayService(db); service.connect(user.id, device.device_id, "session", ["desktop.open_application"])
        command = service.submit(user, contract(user))
        assert command.status == "QUEUED" and service.pending(user.id, device.device_id) == [command]
        service.delivered(command)
        completed = service.complete(user.id, device.device_id, DeviceCapabilityResult(
            request_id="request-1", status="completed", output={"opened": "Chrome"}, verification={"verified": True},
        ))
        assert completed.status == "COMPLETED" and completed.result_json["output"]["opened"] == "Chrome"


def test_duplicate_request_is_idempotent_per_user_but_not_global():
    with Session() as db:
        first, first_device = seed(db, "one@example.com", "one-device")
        second, second_device = seed(db, "two@example.com", "two-device")
        service = DeviceGatewayService(db)
        service.connect(first.id, "one-device", "one-session", [])
        service.connect(second.id, "two-device", "two-session", [])
        one = service.submit(first, contract(first, "one-device", "same"))
        duplicate = service.submit(first, contract(first, "one-device", "same"))
        two = service.submit(second, contract(second, "two-device", "same"))
        assert one.id == duplicate.id and two.id != one.id


def test_expired_command_becomes_timeout_and_is_not_delivered():
    with Session() as db:
        user, device = seed(db)
        service = DeviceGatewayService(db); service.connect(user.id, device.device_id, "session", [])
        command = service.submit(user, contract(user))
        command.expires_at = utc_now() - timedelta(seconds=1); db.commit()
        assert service.pending(user.id, device.device_id) == []
        assert command.status == "TIMEOUT" and command.safe_error


def test_disconnect_requeues_delivered_command_for_reconnect():
    with Session() as db:
        user, _ = seed(db)
        service = DeviceGatewayService(db); service.connect(user.id, "device-1", "session", [])
        command = service.submit(user, contract(user)); service.delivered(command)
        service.disconnect(user.id, "device-1", "session")
        assert command.status == "WAITING_FOR_DEVICE"


def test_revoked_device_rejects_new_commands_and_connection():
    with Session() as db:
        user, device = seed(db); device.revoked_at = utc_now(); db.commit()
        service = DeviceGatewayService(db)
        with pytest.raises(PermissionError):
            service.connect(user.id, device.device_id, "session", [])
        with pytest.raises(PermissionError):
            service.submit(user, contract(user))


def test_cross_user_device_and_result_are_rejected():
    with Session() as db:
        owner, _ = seed(db, "owner@example.com", "owner-device")
        other, _ = seed(db, "other@example.com", "other-device")
        service = DeviceGatewayService(db)
        service.connect(owner.id, "owner-device", "owner-session", [])
        service.connect(other.id, "other-device", "other-session", [])
        with pytest.raises(LookupError):
            service.submit(other, contract(other, "owner-device"))
        service.submit(owner, contract(owner, "owner-device"))
        with pytest.raises(LookupError):
            service.complete(other.id, "other-device", DeviceCapabilityResult(request_id="request-1", status="failed"))


def test_unadvertised_capability_is_rejected():
    with Session() as db:
        user, device = seed(db)
        service = DeviceGatewayService(db); service.connect(user.id, device.device_id, "session", ["media.pause"])
        with pytest.raises(LookupError):
            service.submit(user, contract(user))


def test_stage23_device_decision_uses_existing_contract_and_gateway():
    with Session() as db:
        user, device = seed(db)
        service = DeviceGatewayService(db); service.connect(user.id, device.device_id, "session", ["desktop.open_application"])
        request = ExecutionRequest(
            request_id="placed", task_id="task", agent_id="friday", capability="desktop.open_application",
            user_id=user.id, device_id=device.device_id, arguments={"name": "Chrome"}, required_target=ExecutionTarget.DEVICE,
        )
        decision = ExecutionDecision(
            request_id="placed", task_id="task", target=ExecutionTarget.DEVICE, device_id=device.device_id,
            reason="authorized_device_online", can_execute_now=True,
        )
        command = PersistentDeviceExecutor(service, user).submit(request, decision)
        assert DeviceCapabilityRequest.model_validate(command.request_json).request_id == "placed"


def test_safe_error_does_not_persist_arbitrary_error_payload():
    with Session() as db:
        user, device = seed(db); service = DeviceGatewayService(db); service.connect(user.id, device.device_id, "session", []); service.submit(user, contract(user))
        command = service.complete(user.id, "device-1", DeviceCapabilityResult(
            request_id="request-1", status="failed", error={"message": "safe", "token": "must-not-be-copied"},
        ))
        assert command.safe_error == "safe"
        assert "token" not in command.safe_error


def test_authenticated_websocket_delivers_and_correlates_result(monkeypatch):
    with Session() as db:
        user, device = seed(db)
        service = DeviceGatewayService(db); service.connect(user.id, device.device_id, "pre-session", [])
        service.submit(user, contract(user))
        user_id = user.id
        device_id = device.device_id

    class Socket:
        headers = {"authorization": "Bearer safe-test-token"}

        def __init__(self):
            self.received = 0
            self.sent = []
            self.accepted = False

        async def accept(self):
            self.accepted = True

        async def close(self, code=1000, reason=""):
            self.sent.append({"closed": code, "reason": reason})

        async def send_json(self, payload):
            self.sent.append(payload)

        async def receive_json(self):
            self.received += 1
            if self.received == 1:
                return {"type": "device.hello", "capabilities": ["desktop.open_application"]}
            if self.received == 2:
                return {"type": "device.capability.result", "payload": {
                    "request_id": "request-1", "status": "completed", "output": {"opened": "Chrome"},
                    "verification": {"verified": True},
                }}
            raise WebSocketDisconnect()

    monkeypatch.setattr("app.services.device_gateway.SessionLocal", Session)
    monkeypatch.setattr("app.services.device_gateway.verify_desktop_access_token", lambda _token: {"sub": user_id, "device_id": device_id})
    socket = Socket()
    asyncio.run(device_gateway.handle(socket))
    with Session() as db:
        command = db.query(DesktopCommand).filter(DesktopCommand.request_id == "request-1").one()
        assert command.status == "COMPLETED"
    delivered = [item for item in socket.sent if item.get("type") == "device.capability.request"]
    assert socket.accepted and delivered[0]["payload"]["request_id"] == "request-1"
