from types import SimpleNamespace

from app.services.orchestrator.knowledge_router import KnowledgeRoute, KnowledgeRouter
from app.services.orchestrator.orchestrator import CeaserOrchestrator
from app.services.orchestrator.response_pipeline import ResponsePipeline


def orchestrator() -> CeaserOrchestrator:
    return CeaserOrchestrator.__new__(CeaserOrchestrator)


def test_another_example_continues_dbms_normalization() -> None:
    resolution = orchestrator()._resolve_conversation_turn("Give me another example.", "DBMS normalization")
    assert resolution["follow_up_detected"] is True
    assert resolution["active_topic"] == "DBMS normalization"
    assert resolution["intent"] == "examples"


def test_python_java_references_remain_on_comparison() -> None:
    service = orchestrator()
    easier = service._resolve_conversation_turn("Which one is easier for beginners?", "Python and Java")
    first = service._resolve_conversation_turn("Give me code for the first one.", "Python and Java")
    assert easier["follow_up_detected"] is True
    assert first["follow_up_detected"] is True
    assert first["active_topic"] == "Python and Java"


def test_study_plan_follow_up_keeps_active_plan() -> None:
    resolution = orchestrator()._resolve_conversation_turn("What should I study tomorrow?", "30-day Python study plan")
    assert resolution["follow_up_detected"] is True
    assert resolution["active_topic"] == "30-day Python study plan"


def test_six_month_resume_uses_persisted_state() -> None:
    service = orchestrator()
    service.conversations = SimpleNamespace(list_recent_messages=lambda **_: [])
    conversation = SimpleNamespace(
        id="old-chat",
        conversation_summary="Topic: Python | Last subject: OOP | Unfinished goal: inheritance",
        conversation_state={"active_topic": "Python", "active_subtopic": "OOP", "unfinished_goal": "inheritance", "important_entities": ["Python"]},
    )
    context = service._conversation_context(conversation)
    trace = service._follow_up_trace(message="Continue from where we stopped.", conversation_context=context, parent_message_id=None)
    assert trace["follow_up_detected"] is True
    assert trace["active_topic"] == "Python"
    assert "conversation_summary" in trace["context_source"]


def test_explicit_topic_switch_overrides_old_topic() -> None:
    service = orchestrator()
    switched = service._resolve_conversation_turn("Now tell me about operating systems.", "DBMS normalization")
    continued = service._resolve_conversation_turn("Give me another example.", switched["active_topic"])
    assert switched["new_topic"] is True
    assert "operating systems" in switched["active_topic"].lower()
    assert continued["active_topic"] == switched["active_topic"]


def test_cross_conversation_memory_is_only_fallback() -> None:
    router = KnowledgeRouter()
    decision = router.classify(
        message="Tell me the startup idea I mentioned months ago.",
        has_attached_files=False,
        is_follow_up=False,
    )
    assert decision.route is KnowledgeRoute.MEMORY


def test_direct_chat_prompt_keeps_bounded_conversation_context() -> None:
    pipeline = ResponsePipeline.__new__(ResponsePipeline)
    instructions, context = pipeline._build_prompt(
        message="Give me another example.",
        context={
            "latest_user_message": "Give me another example.",
            "knowledge_context": {"intent": "general_chat", "retrieval_scope": "none", "evidence": ""},
            "conversation": [
                {"role": "user", "content": "Explain DBMS normalization."},
                {"role": "assistant", "content": "Normalization organizes relational data."},
            ],
            "conversation_summary": "Topic: DBMS normalization",
            "follow_up_trace": {"follow_up_detected": True, "active_topic": "DBMS normalization"},
        },
    )
    assert "context-persistent" in instructions
    assert "Explain DBMS normalization" in context
    assert "Topic: DBMS normalization" in context
