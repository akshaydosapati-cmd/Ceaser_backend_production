from app.intelligence.ai.model_router.models import Workload
from app.services.orchestrator.response_pipeline import ResponsePipeline


def test_direct_coding_chat_requests_bolt_workload():
    request = ResponsePipeline()._model_request(
        message="Create a responsive landing page in HTML CSS and JavaScript",
        context={},
        streaming=True,
        context_text="request",
    )

    assert request.agent_id == "bolt"
    assert request.workload is Workload.SOFTWARE_ENGINEERING
    assert "coding" in request.required_capabilities


def test_normal_chat_stays_normal_chat():
    request = ResponsePipeline()._model_request(
        message="Explain recursion simply",
        context={},
        streaming=True,
        context_text="request",
    )

    assert request.agent_id is None
    assert request.workload is Workload.NORMAL_CHAT


def test_manual_model_preference_is_preserved_for_coding():
    request = ResponsePipeline()._model_request(
        message="Write a Python REST API",
        context={"model_preference": "openai-primary"},
        streaming=True,
        context_text="request",
    )

    assert request.agent_id == "bolt"
    assert request.preferred_model_ids == frozenset({"openai-primary"})
