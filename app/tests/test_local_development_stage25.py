from app.agents.v2 import ExecutionTarget
from app.execution.placement import DeviceAvailability, ExecutionPlacementEngine, ExecutionRequest, PlacementFailure
from app.services.capabilities.registry import capability_registry


def test_stage25_local_capability_contract_and_placement():
    required = {
        "bolt.execute_plan", "project.create", "project.open", "project.inspect", "project.list_files",
        "project.read_file", "project.write_file", "project.patch_file", "project.build", "project.test",
        "terminal.run_scoped", "git.init", "git.status", "git.diff", "git.add", "git.commit", "vscode.open_project",
    }
    assert required.issubset({item.id for item in capability_registry.list()})
    assert capability_registry.get("project.delete").requires_confirmation
    assert capability_registry.get("git.commit").requires_confirmation

    request = ExecutionRequest(
        request_id="stage25", task_id="bolt-task", agent_id="bolt", capability="bolt.execute_plan",
        user_id="user-a", required_target=ExecutionTarget.DEVICE,
        metadata={"workload": "software_engineering"},
    )
    eligible = DeviceAvailability(
        device_id="device-a", user_id="user-a", connected=True, authenticated=True, authorized=True,
        advertised_capabilities=frozenset({"bolt.execute_plan"}),
    )
    decision = ExecutionPlacementEngine().place(request, devices=[eligible])
    assert decision.target == ExecutionTarget.DEVICE and decision.device_id == "device-a" and decision.can_execute_now

    other = eligible.model_copy(update={"user_id": "user-b"})
    denied = ExecutionPlacementEngine().place(request, devices=[other])
    assert denied.requires_wait and denied.failure == PlacementFailure.NO_DEVICE
