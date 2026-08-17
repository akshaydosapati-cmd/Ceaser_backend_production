import pytest

from app.agents.v2 import (
    AgentContextBuilder, AgentOrchestrator, AgentRegistry, AgentResult, AgentSelector, AgentTaskStatus,
    DeviceCapabilityRequest, DeviceCapabilityResult, ExecutionTarget,
)
from app.agents.v2.models import VerificationEvidence


@pytest.mark.parametrize(("message", "agent"), [
    ("Build a dental clinic website", "bolt"), ("Fix my React project", "bolt"),
    ("Write HTML code for a login screen", "bolt"), ("Give me a Python function that validates email addresses", "bolt"),
    ("Research the Indian EV market", "alex"), ("Create campaign concepts", "nova"),
    ("Plan our startup launch strategy", "zeus"), ("Organize these documents", "atlas"),
    ("Plan my work tomorrow", "friday"),
])
def test_specialist_selection(message, agent):
    result = AgentSelector().select(message)
    assert result.route == "SPECIALIST"
    assert agent in result.agent_ids


@pytest.mark.parametrize("message", ["What is quantum computing?", "Explain photosynthesis"])
def test_general_knowledge_bypasses_specialists(message):
    assert AgentSelector().select(message).route == "NORMAL_AI"


@pytest.mark.parametrize("message", ["Open Chrome", "Pause music"])
def test_direct_device_commands_bypass_specialists(message):
    result = AgentSelector().select(message)
    assert result.route == "DIRECT_DEVICE"
    assert result.execution_target == ExecutionTarget.DEVICE


def test_registry_definitions_and_permissions():
    registry = AgentRegistry()
    assert {item.id for item in registry.enabled()} == {"bolt", "alex", "friday", "nova", "zeus", "atlas"}
    assert registry.capability_allowed("bolt", "terminal.run") is True
    assert registry.capability_allowed("nova", "terminal.run") is False


def test_confirmation_cannot_be_bypassed():
    orchestrator = AgentOrchestrator()
    assert orchestrator.capability_allowed("bolt", "deployment.run", user_authorized=True, confirmed=False, requires_confirmation=True) is False


def test_context_is_scoped_and_bounded():
    definition = AgentRegistry().get("bolt")
    context = AgentContextBuilder().build(definition, "Fix it", {
        "conversation": list(range(20)), "active_project": {"id": "p1"},
        "relevant_memories": [{"id": "stale"}], "unrelated_project": {"id": "p2"},
        "available_capabilities": ["terminal.run", "billing.charge"],
    })
    assert context["conversation"] == list(range(12, 20))
    assert context["active_project"]["id"] == "p1"
    assert "unrelated_project" not in context and "memories" not in context
    assert context["available_capabilities"] == ["terminal.run"]


def test_follow_up_retains_agent_but_new_command_exits_context():
    selector = AgentSelector()
    assert selector.select("Make the hero more premium", active_agent_id="bolt").agent_ids == ["bolt"]
    assert selector.select("Open Calculator", active_agent_id="bolt").route == "DIRECT_DEVICE"


def test_channel_parity():
    selector = AgentSelector()
    selections = [selector.select("Build a dental clinic website", channel=channel).agent_ids for channel in ("voice", "text", "web")]
    assert selections[0] == selections[1] == selections[2] == ["bolt"]


def test_bolt_code_response_uses_large_output_budget():
    from app.services.orchestrator.response_pipeline import ResponsePipeline

    context = {"merged_contributions": {"selected_agents": ["Bolt"]}}
    assert ResponsePipeline._stream_output_budget(message="Write an animated login page", context=context) == 6000


def test_specialist_preparation_uses_existing_model_context_path():
    orchestrator = AgentOrchestrator()
    prepared = orchestrator.prepare(
        "Build a dental clinic website",
        {"active_project": {"id": "project-1"}, "available_capabilities": ["project", "build", "test"]},
    )
    assert prepared is not None
    assert prepared["status"] == "planning"
    assert prepared["agents"][0]["definition"]["id"] == "bolt"
    assert prepared["agents"][0]["context"]["active_project"]["id"] == "project-1"
    assert [event.event for event in orchestrator.events] == ["agent.selected", "agent.planning"]


def test_device_contract_serialization_and_failure_timeout():
    request = DeviceCapabilityRequest(request_id="r1", task_id="t1", agent_id="bolt", device_id="d1", capability="project.read", authorization={"user_id": "u1"})
    assert DeviceCapabilityRequest.model_validate_json(request.model_dump_json()) == request
    for status in ("failed", "timeout"):
        result = DeviceCapabilityResult(request_id="r1", status=status, error={"code": status})
        assert DeviceCapabilityResult.model_validate_json(result.model_dump_json()).status == status


def test_bounded_delegation_and_duplicate_prevention():
    orchestrator = AgentOrchestrator(max_agents=2)
    calls = []
    def runner(agent_id, _context):
        calls.append(agent_id)
        return AgentResult(task_id="t1", agent_id=agent_id, status=AgentTaskStatus.COMPLETED, summary="done", verification=VerificationEvidence(verified=True, checks=[{"ok": True}]))
    results = orchestrator.run("Research competitors and create a launch strategy", {}, runner)
    assert calls == ["alex", "zeus"]
    assert len(results) == 2


def test_failed_verification_cannot_report_success():
    with pytest.raises(ValueError, match="verified evidence"):
        AgentResult(task_id="t1", agent_id="bolt", status=AgentTaskStatus.COMPLETED, summary="done")
