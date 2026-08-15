import pytest

from app.core.config.settings import settings

from app.agents.v2 import AgentOrchestrator, DeviceCapabilityResult, ExecutionTarget
from app.execution.placement import (
    CloudAvailability, CloudExecutor, DeviceAvailability, ExecutionPlacementEngine, ExecutionRequest,
    PlacementFailure, PlacementPolicy, ProjectExecutionContext,
)
from app.services.capabilities.registry import capability_registry


def req(capability, *, target=ExecutionTarget.EITHER, project=None, confirm=False, confirmed=False, device_id=None, agent="bolt"):
    return ExecutionRequest(
        request_id="r1", task_id="t1", agent_id=agent, capability=capability, user_id="u1",
        required_target=target, project_context=project, requires_confirmation=confirm, confirmed=confirmed,
        device_id=device_id,
    )


def device(*, online=True, authorized=True, capabilities=()):
    return DeviceAvailability(
        device_id="d1", user_id="u1", connected=online, authenticated=authorized, authorized=authorized,
        advertised_capabilities=frozenset(capabilities),
    )


@pytest.mark.parametrize(("capability", "target"), [
    ("desktop.open_application", ExecutionTarget.DEVICE),
    ("media.pause", ExecutionTarget.DEVICE),
    ("strategy.reason", ExecutionTarget.NONE),
    ("cloud.workspace.build", ExecutionTarget.CLOUD),
])
def test_capability_target_metadata(capability, target):
    assert target in capability_registry.get(capability).allowed_execution_targets


def test_project_build_supports_device_and_cloud():
    targets = set(capability_registry.get("project.build").allowed_execution_targets)
    assert targets == {ExecutionTarget.DEVICE, ExecutionTarget.CLOUD}


def test_required_device_online_authorized_is_executable():
    result = ExecutionPlacementEngine().place(req("desktop.open_application", target=ExecutionTarget.DEVICE), devices=[device()])
    assert result.target == ExecutionTarget.DEVICE and result.can_execute_now and result.device_id == "d1"


@pytest.mark.parametrize(("available", "failure"), [
    (device(online=False), PlacementFailure.DEVICE_OFFLINE),
    (device(authorized=False), PlacementFailure.DEVICE_UNAUTHORIZED),
])
def test_device_failure_is_structured(available, failure):
    result = ExecutionPlacementEngine().place(req("desktop.open_application", target=ExecutionTarget.DEVICE), devices=[available])
    assert result.failure == failure and not result.can_execute_now


def test_requested_missing_device_is_not_silently_replaced():
    result = ExecutionPlacementEngine().place(req("desktop.open_application", device_id="other"), devices=[device()])
    assert result.failure == PlacementFailure.NO_DEVICE


@pytest.mark.parametrize(("project", "policy", "target"), [
    (ProjectExecutionContext(project_id="p", local_path="C:/repo", device_id="d1"), PlacementPolicy.AUTO, ExecutionTarget.DEVICE),
    (ProjectExecutionContext(project_id="p", cloud_workspace_id="cw"), PlacementPolicy.AUTO, ExecutionTarget.CLOUD),
    (ProjectExecutionContext(project_id="p", local_path="C:/repo", cloud_workspace_id="cw"), PlacementPolicy.LOCAL_FIRST, ExecutionTarget.DEVICE),
    (ProjectExecutionContext(project_id="p", local_path="C:/repo", cloud_workspace_id="cw"), PlacementPolicy.CLOUD_FIRST, ExecutionTarget.CLOUD),
    (ProjectExecutionContext(project_id="p", local_path="C:/repo", cloud_workspace_id="cw"), PlacementPolicy.AUTO, ExecutionTarget.DEVICE),
])
def test_project_location_and_policy(project, policy, target, monkeypatch):
    monkeypatch.setattr(settings, "cloud_coding_enabled", True)
    result = ExecutionPlacementEngine().place(
        req("project.build", project=project), devices=[device()], cloud=CloudAvailability(available=True), policy=policy,
    )
    assert result.target == target


def test_either_uses_cloud_when_device_unavailable(monkeypatch):
    monkeypatch.setattr(settings, "cloud_coding_enabled", True)
    result = ExecutionPlacementEngine().place(
        req("project.build"), devices=[device(online=False)], cloud=CloudAvailability(available=True),
    )
    assert result.target == ExecutionTarget.CLOUD


def test_either_with_no_environment_is_unavailable(monkeypatch):
    monkeypatch.setattr(settings, "cloud_coding_enabled", True)
    result = ExecutionPlacementEngine().place(req("project.build"))
    assert result.failure == PlacementFailure.NO_COMPATIBLE_TARGET


def test_project_without_location_is_explicit_failure(monkeypatch):
    monkeypatch.setattr(settings, "cloud_coding_enabled", True)
    result = ExecutionPlacementEngine().place(req("project.build", project=ProjectExecutionContext(project_id="p")))
    assert result.failure == PlacementFailure.PROJECT_NOT_AVAILABLE


def test_confirmation_cannot_be_bypassed():
    result = ExecutionPlacementEngine().place(req("project.build", confirm=True), devices=[device()])
    assert result.failure == PlacementFailure.CONFIRMATION_REQUIRED and result.requires_confirmation


def test_agent_and_direct_command_placement():
    engine = ExecutionPlacementEngine()
    direct = engine.place(req("desktop.open_application", agent="ceaser"), devices=[device()])
    bolt = AgentOrchestrator().place_action(req("project.build"), devices=[device()])
    zeus = engine.place(req("strategy.reason", agent="zeus"))
    friday = engine.place(req("desktop.open_application", agent="friday"), devices=[device()])
    assert direct.target == bolt.target == friday.target == ExecutionTarget.DEVICE
    assert zeus.target == ExecutionTarget.NONE and zeus.can_execute_now


def test_device_contract_and_verified_agent_result():
    engine = ExecutionPlacementEngine()
    request = req("desktop.open_application")
    decision = engine.place(request, devices=[device()])
    device_request = engine.to_device_request(request, decision)
    assert device_request.capability == request.capability and device_request.device_id == "d1"
    execution = engine.device_result(request, DeviceCapabilityResult(
        request_id="r1", status="completed", output={"opened": "Chrome"}, verification={"verified": True},
    ))
    agent = engine.into_agent_result(execution, agent_id="friday", summary="Chrome opened")
    assert agent.status.value == "completed" and agent.verification.verified


def test_cloud_boundary_never_fakes_completion():
    executor = CloudExecutor()
    result = executor.submit(req("cloud.workspace.build", target=ExecutionTarget.CLOUD))
    assert result.status == "deferred" and not result.verification
    assert result.error["code"] == PlacementFailure.CLOUD_UNAVAILABLE.value


def test_cloud_placement_reports_stage24_unavailable():
    engine = ExecutionPlacementEngine()
    decision = engine.place(
        req("cloud.workspace.build", target=ExecutionTarget.CLOUD), cloud=CloudAvailability(available=True),
    )
    assert decision.target == ExecutionTarget.CLOUD and decision.requires_wait
    assert decision.failure == PlacementFailure.CLOUD_UNAVAILABLE and not decision.can_execute_now


def test_unregistered_and_unadvertised_capabilities_fail_safely():
    engine = ExecutionPlacementEngine()
    missing = engine.place(req("unknown.capability"), devices=[device()])
    unadvertised = engine.place(
        req("desktop.open_application"), devices=[device(capabilities={"media.pause"})],
    )
    assert missing.failure == unadvertised.failure == PlacementFailure.CAPABILITY_UNAVAILABLE


def test_safe_observability_events():
    engine = ExecutionPlacementEngine()
    engine.place(req("desktop.open_application"), devices=[device()])
    events = [event.event for event in engine.events]
    assert events == ["execution.placement_requested", "execution.target_selected", "execution.device_selected"]
    assert "arguments" not in engine.events[0].metadata
