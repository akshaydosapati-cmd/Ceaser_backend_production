from __future__ import annotations

from app.agents.v2.device_contract import DeviceCapabilityRequest, DeviceCapabilityResult
from app.agents.v2.models import AgentResult, AgentTaskStatus, ExecutionTarget, VerificationEvidence
from app.services.capabilities.registry import CapabilityRegistry, capability_registry
from app.core.config.settings import settings

from .models import (
    CloudAvailability, DeviceAvailability, ExecutionDecision, ExecutionPlacementEvent, ExecutionRequest,
    ExecutionResult, PlacementFailure, PlacementPolicy,
)


class CloudExecutor:
    """Stage 24 boundary. It must not report successful cloud execution in Stage 23."""

    available = False

    def submit(self, request: ExecutionRequest) -> ExecutionResult:
        return ExecutionResult(
            request_id=request.request_id, task_id=request.task_id, target_used=ExecutionTarget.CLOUD,
            executor="stage24_cloud_worker", status="deferred",
            error={"code": PlacementFailure.CLOUD_UNAVAILABLE.value, "message": "Cloud workers are not available until Stage 24."},
        )


class ExecutionPlacementEngine:
    def __init__(self, registry: CapabilityRegistry | None = None, cloud_executor: CloudExecutor | None = None):
        self.registry = registry or capability_registry
        self.cloud_executor = cloud_executor or CloudExecutor()
        self.events: list[ExecutionPlacementEvent] = []

    def place(
        self, request: ExecutionRequest, *, devices: list[DeviceAvailability] | None = None,
        cloud: CloudAvailability | None = None, policy: PlacementPolicy = PlacementPolicy.AUTO,
    ) -> ExecutionDecision:
        self._event("execution.placement_requested", request)
        capability = self.registry.get(request.capability)
        if capability is None:
            return self._failure(request, PlacementFailure.CAPABILITY_UNAVAILABLE, "capability_not_registered")

        allowed = set(capability.allowed_execution_targets)
        candidates = self._required_candidates(request.required_target, allowed)
        coding_request = self._is_software_engineering(request)
        if coding_request and not settings.cloud_coding_enabled:
            if request.required_target == ExecutionTarget.CLOUD:
                self._event("execution.cloud_coding_disabled", request, ExecutionTarget.CLOUD, "v1_cloud_coding_disabled")
                return self._failure(request, PlacementFailure.CLOUD_CODING_DISABLED, "v1_cloud_coding_disabled", target=ExecutionTarget.CLOUD)
            candidates.discard(ExecutionTarget.CLOUD)
            if ExecutionTarget.DEVICE in allowed and settings.local_coding_enabled:
                candidates.add(ExecutionTarget.DEVICE)
                policy = PlacementPolicy.LOCAL_FIRST
                self._event("execution.local_first_selected", request, ExecutionTarget.DEVICE, "v1_software_engineering_policy")
        if not candidates:
            return self._failure(request, PlacementFailure.NO_COMPATIBLE_TARGET, "required_target_not_allowed")
        if candidates == {ExecutionTarget.NONE}:
            return self._selected(request, ExecutionTarget.NONE, "reasoning_only", can_execute=True)
        if request.requires_confirmation and not request.confirmed:
            target = self._preferred_candidate(candidates, request, policy)
            return self._failure(
                request, PlacementFailure.CONFIRMATION_REQUIRED, "confirmation_required", target=target,
                requires_confirmation=True,
            )

        device, device_failure = self._device(request, devices or [])
        cloud_state = cloud or CloudAvailability()
        ordered = self._ordered_targets(candidates, request, policy, device, cloud_state)
        for target in ordered:
            if target == ExecutionTarget.DEVICE and device is not None:
                if device.advertised_capabilities and request.capability not in device.advertised_capabilities:
                    device_failure = PlacementFailure.CAPABILITY_UNAVAILABLE
                    continue
                return self._selected(request, target, "compatible_authorized_device_online", device_id=device.device_id, can_execute=True)
            if target == ExecutionTarget.CLOUD and cloud_state.available:
                if cloud_state.advertised_capabilities and request.capability not in cloud_state.advertised_capabilities:
                    continue
                return self._selected(request, target, "compatible_cloud_environment", can_execute=self.cloud_executor.available)

        if ExecutionTarget.DEVICE in candidates and ExecutionTarget.CLOUD not in candidates:
            return self._failure(request, device_failure or PlacementFailure.NO_DEVICE, "coding_device_required" if coding_request else "required_device_unavailable", target=ExecutionTarget.DEVICE, wait=True)
        if ExecutionTarget.CLOUD in candidates and ExecutionTarget.DEVICE not in candidates:
            return self._failure(request, PlacementFailure.CLOUD_UNAVAILABLE, "cloud_executor_deferred_until_stage24", target=ExecutionTarget.CLOUD, wait=True)
        if request.project_context and not request.project_context.local_path and not request.project_context.cloud_workspace_id:
            return self._failure(request, PlacementFailure.PROJECT_NOT_AVAILABLE, "project_has_no_execution_location")
        if device_failure == PlacementFailure.DEVICE_UNAUTHORIZED and not cloud_state.available:
            return self._failure(request, device_failure, "device_unauthorized_and_cloud_unavailable")
        return self._failure(request, PlacementFailure.NO_COMPATIBLE_TARGET, "no_compatible_environment", wait=True)

    def to_device_request(self, request: ExecutionRequest, decision: ExecutionDecision) -> DeviceCapabilityRequest:
        if decision.target != ExecutionTarget.DEVICE or not decision.device_id or not decision.can_execute_now:
            raise ValueError("Execution decision is not an executable device placement")
        confirmation = "already_confirmed" if request.confirmed else ("required" if request.requires_confirmation else "none")
        self._event("execution.device_requested", request, decision.target, decision.reason)
        return DeviceCapabilityRequest(
            request_id=request.request_id, task_id=request.task_id, agent_id=request.agent_id,
            device_id=decision.device_id, capability=request.capability, arguments=request.arguments,
            confirmation_requirement=confirmation, timeout_seconds=request.timeout_seconds,
            authorization={"user_id": request.user_id}, metadata={"placement_reason": decision.reason},
        )

    def device_result(self, request: ExecutionRequest, result: DeviceCapabilityResult) -> ExecutionResult:
        mapped = ExecutionResult(
            request_id=result.request_id, task_id=request.task_id, target_used=ExecutionTarget.DEVICE,
            executor="desktop_companion", status=result.status, output=result.output, error=result.error,
            verification=result.verification, metadata=result.metadata,
        )
        self._event("execution.completed" if result.status == "completed" else "execution.failed", request, ExecutionTarget.DEVICE, result.status)
        return mapped

    @staticmethod
    def into_agent_result(result: ExecutionResult, *, agent_id: str, summary: str) -> AgentResult:
        completed = result.status == "completed" and bool(result.verification.get("verified"))
        if completed:
            status = AgentTaskStatus.COMPLETED
        elif result.status == "deferred" and result.target_used == ExecutionTarget.CLOUD:
            status = AgentTaskStatus.WAITING_FOR_CLOUD
        elif result.status == "deferred":
            status = AgentTaskStatus.WAITING_FOR_DEVICE
        else:
            status = AgentTaskStatus.FAILED
        return AgentResult(
            task_id=result.task_id, agent_id=agent_id, status=status, summary=summary,
            outputs=[result.output] if result.output else [], execution_targets_used=[result.target_used],
            verification=VerificationEvidence(verified=completed, checks=[result.verification] if result.verification else [], summary=summary),
            blockers=[result.error.get("code", "execution_failed")] if result.error else [],
            metadata={"execution": result.model_dump(mode="json")},
        )

    @staticmethod
    def _required_candidates(required: ExecutionTarget, allowed: set[ExecutionTarget]) -> set[ExecutionTarget]:
        if required == ExecutionTarget.EITHER:
            return allowed
        return {required} if required in allowed else set()

    def _device(self, request: ExecutionRequest, devices: list[DeviceAvailability]):
        scoped = [item for item in devices if item.user_id == request.user_id]
        requested = request.device_id or (request.project_context.device_id if request.project_context else None)
        if requested:
            scoped = [item for item in scoped if item.device_id == requested]
        if not scoped:
            return None, PlacementFailure.NO_DEVICE
        authorized = [item for item in scoped if item.authenticated and item.authorized]
        if not authorized:
            return None, PlacementFailure.DEVICE_UNAUTHORIZED
        online = [item for item in authorized if item.connected]
        if not online:
            return None, PlacementFailure.DEVICE_OFFLINE
        capable = [item for item in online if not item.advertised_capabilities or request.capability in item.advertised_capabilities]
        if not capable:
            return None, PlacementFailure.CAPABILITY_UNAVAILABLE
        if len(capable) == 1:
            return capable[0], None
        preferred = [item for item in capable if item.preferred]
        if len(preferred) == 1:
            return preferred[0], None
        return None, PlacementFailure.AMBIGUOUS_DEVICE

    @staticmethod
    def _is_software_engineering(request: ExecutionRequest) -> bool:
        workload = str(request.metadata.get("workload") or "").lower()
        if workload == "software_engineering":
            return True
        return request.agent_id.lower() == "bolt" and request.capability.split(".", 1)[0] in {
            "project", "filesystem", "terminal", "git", "build", "test", "development",
        }

    @staticmethod
    def _preferred_candidate(candidates, request, policy):
        return ExecutionPlacementEngine._ordered_targets(candidates, request, policy, None, CloudAvailability())[0]

    @staticmethod
    def _ordered_targets(candidates, request, policy, device, cloud):
        project = request.project_context
        if project:
            if project.local_path and not project.cloud_workspace_id:
                return [ExecutionTarget.DEVICE]
            if project.cloud_workspace_id and not project.local_path:
                return [ExecutionTarget.CLOUD]
        preferred = request.preferred_target
        if preferred in candidates:
            first = preferred
        elif policy == PlacementPolicy.CLOUD_FIRST:
            first = ExecutionTarget.CLOUD
        elif policy == PlacementPolicy.LOCAL_FIRST:
            first = ExecutionTarget.DEVICE
        else:
            first = ExecutionTarget.DEVICE if device is not None else ExecutionTarget.CLOUD
        return [target for target in (first, ExecutionTarget.CLOUD if first == ExecutionTarget.DEVICE else ExecutionTarget.DEVICE) if target in candidates]

    def _selected(self, request, target, reason, *, device_id=None, can_execute=False):
        decision = ExecutionDecision(
            request_id=request.request_id, task_id=request.task_id, target=target, reason=reason,
            device_id=device_id, can_execute_now=can_execute,
            requires_wait=target == ExecutionTarget.CLOUD and not can_execute,
            failure=PlacementFailure.CLOUD_UNAVAILABLE if target == ExecutionTarget.CLOUD and not can_execute else None,
            fallback_target=None,
        )
        self._event("execution.target_selected", request, target, reason)
        if target == ExecutionTarget.CLOUD:
            self._event("execution.cloud_requested", request, target, reason)
        elif target == ExecutionTarget.DEVICE:
            self._event("execution.device_selected", request, target, reason, {"device_id": device_id})
        return decision

    def _failure(self, request, failure, reason, *, target=ExecutionTarget.NONE, wait=False, requires_confirmation=False):
        decision = ExecutionDecision(
            request_id=request.request_id, task_id=request.task_id, target=target, reason=reason,
            can_execute_now=False, requires_wait=wait, requires_confirmation=requires_confirmation, failure=failure,
            metadata={"user_message": "Your CEASER Desktop Companion needs to be online and capable of this action."} if wait and target == ExecutionTarget.DEVICE else {},
        )
        event = "execution.waiting_for_device" if wait and target == ExecutionTarget.DEVICE else "execution.failed"
        self._event(event, request, target, reason, {"failure": failure.value})
        return decision

    def _event(self, event, request, target=None, reason=None, metadata=None):
        self.events.append(ExecutionPlacementEvent(
            event=event, task_id=request.task_id, agent_id=request.agent_id, capability=request.capability,
            target=target, reason=reason, metadata={"user_id": request.user_id, **(metadata or {})},
        ))
