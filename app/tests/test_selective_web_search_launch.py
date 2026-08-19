from app.services.orchestrator.knowledge_router import KnowledgeRoute
from app.services.orchestrator.orchestrator import CeaserOrchestrator


def test_live_search_is_selective_and_memory_first():
    assert CeaserOrchestrator._should_run_live_research(
        route=KnowledgeRoute.RESEARCH,
        has_internal_context=False,
    ) is True
    assert CeaserOrchestrator._should_run_live_research(
        route=KnowledgeRoute.GENERAL,
        has_internal_context=False,
    ) is False
    assert CeaserOrchestrator._should_run_live_research(
        route=KnowledgeRoute.RESEARCH,
        has_internal_context=True,
    ) is False
