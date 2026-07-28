from app.services.orchestrator.suggestion_engine import SuggestionEngine


def test_suggestion_engine_generates_contextual_education_suggestions() -> None:
    engine = SuggestionEngine()

    suggestions = engine.generate(
        user_query="Create a 7 day study plan for physics",
        response_text="Here is a 7 day study schedule for mechanics, optics, and thermodynamics.",
        intent="general_question",
        retrieval_scope="none",
        output_format="table",
        conversation_context={"inferred_topic": "physics exam prep"},
        recent_suggestions=[],
    )

    texts = [item.text for item in suggestions]
    assert texts
    assert any("study" in item.lower() or "revision" in item.lower() or "flashcards" in item.lower() for item in texts)
    assert len(texts) <= 5


def test_suggestion_engine_avoids_recent_duplicates_and_falls_back() -> None:
    engine = SuggestionEngine()

    suggestions = engine.generate(
        user_query="Explain this topic",
        response_text="This is a general explanation.",
        intent="general_question",
        retrieval_scope="none",
        output_format="chat",
        conversation_context={},
        recent_suggestions=[
            "Summarize this",
            "Explain in more detail",
            "Compare with another topic",
        ],
    )

    texts = [item.text for item in suggestions]
    assert texts
    assert len(set(texts)) == len(texts)


def test_suggestion_engine_handles_story_queries_without_study_prompts() -> None:
    engine = SuggestionEngine()

    suggestions = engine.generate(
        user_query="Explain about Ravanasura",
        response_text="Ravanasura is a major character in the Ramayana. His story shows power, pride, devotion, and downfall.",
        intent="general_question",
        retrieval_scope="none",
        output_format="chat",
        conversation_context={},
        recent_suggestions=[],
    )

    texts = [item.text.lower() for item in suggestions]
    assert texts
    assert not any("timetable" in item or "flashcard" in item for item in texts)
    assert any("traits" in item or "story" in item or "lessons" in item or "simply" in item for item in texts)
