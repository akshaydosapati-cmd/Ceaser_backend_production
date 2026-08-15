from __future__ import annotations

from app.execution.placement import ExecutionDecision, ExecutionPlacementEngine, ExecutionRequest
from app.agents.v2 import ExecutionTarget
from app.models.user import User
from app.services.device_gateway_service import DeviceGatewayService


class PersistentDeviceExecutor:
    """Stage 23 DEVICE decision adapter using the existing device contract."""

    def __init__(self, service: DeviceGatewayService, user: User):
        self.service = service
        self.user = user

    def submit(self, request: ExecutionRequest, decision: ExecutionDecision):
        if request.user_id != self.user.id or decision.target != ExecutionTarget.DEVICE:
            raise PermissionError("Invalid device execution placement")
        contract = ExecutionPlacementEngine().to_device_request(request, decision)
        return self.service.submit(self.user, contract)
