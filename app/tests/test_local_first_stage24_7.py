from app.agents.v2 import AgentSelector, ExecutionTarget
from app.core.config.settings import settings
from app.execution.placement import CloudAvailability, DeviceAvailability, ExecutionPlacementEngine, ExecutionRequest, PlacementFailure


def test_stage24_7_v1_local_first_contract(monkeypatch):
    def request(*, user="user-a", target=ExecutionTarget.EITHER):
        return ExecutionRequest(
            request_id="request", task_id="task", agent_id="bolt", capability="project.build",
            user_id=user, required_target=target, metadata={"workload": "software_engineering"},
        )

    def device(device_id, *, user="user-a", online=True, authorized=True, capable=True, preferred=False):
        return DeviceAvailability(
            device_id=device_id, user_id=user, connected=online, authenticated=authorized, authorized=authorized,
            advertised_capabilities=frozenset({"project.build"} if capable else {"desktop.open_application"}),
            preferred=preferred,
        )

    monkeypatch.setattr(settings, "local_coding_enabled", True)
    monkeypatch.setattr(settings, "cloud_coding_enabled", False)

    engine = ExecutionPlacementEngine()
    online = engine.place(request(), devices=[device("coding-laptop")], cloud=CloudAvailability(available=True))
    assert online.target == ExecutionTarget.DEVICE and online.device_id == "coding-laptop" and online.can_execute_now
    assert "execution.local_first_selected" in [event.event for event in engine.events]
    assert "execution.device_selected" in [event.event for event in engine.events]

    offline = ExecutionPlacementEngine().place(request(), devices=[device("offline", online=False)], cloud=CloudAvailability(available=True))
    assert offline.target == ExecutionTarget.DEVICE and offline.requires_wait
    assert offline.failure == PlacementFailure.DEVICE_OFFLINE and offline.metadata["user_message"]

    isolated = ExecutionPlacementEngine().place(
        request(), devices=[device("other-user", user="user-b"), device("revoked", authorized=False)],
        cloud=CloudAvailability(available=True),
    )
    assert isolated.target == ExecutionTarget.DEVICE and not isolated.can_execute_now
    assert isolated.failure == PlacementFailure.DEVICE_UNAUTHORIZED

    ambiguous = ExecutionPlacementEngine().place(request(), devices=[device("one"), device("two")])
    preferred = ExecutionPlacementEngine().place(request(), devices=[device("one"), device("two", preferred=True)])
    assert ambiguous.failure == PlacementFailure.AMBIGUOUS_DEVICE
    assert preferred.device_id == "two" and preferred.can_execute_now

    explicit_cloud_disabled = ExecutionPlacementEngine().place(request(target=ExecutionTarget.CLOUD), cloud=CloudAvailability(available=True))
    assert explicit_cloud_disabled.failure == PlacementFailure.CLOUD_CODING_DISABLED

    monkeypatch.setattr(settings, "cloud_coding_enabled", True)
    cloud_engine = ExecutionPlacementEngine(cloud_executor=type("Cloud", (), {"available": True})())
    cloud = cloud_engine.place(
        request(target=ExecutionTarget.CLOUD),
        cloud=CloudAvailability(available=True, advertised_capabilities=frozenset({"project.build"})),
    )
    assert cloud.target == ExecutionTarget.CLOUD and cloud.can_execute_now

    assert AgentSelector().select("What is quantum computing?").route == "NORMAL_AI"
    direct = AgentSelector().select("Open Chrome")
    assert direct.route == "DIRECT_DEVICE" and direct.execution_target == ExecutionTarget.DEVICE