from app.intelligence.ai.model_router.models import ModelRequest, RoutingPolicy, Workload
from app.intelligence.ai.model_router.router import ModelRouter
from app.intelligence.ai.model_router.registry import ModelRegistry
from app.services.orchestrator.knowledge_router import KnowledgeRoute, KnowledgeRouter
from app.services.orchestrator.orchestrator import CeaserOrchestrator


def test_ordinary_chat_does_not_request_live_research() -> None:
    decision = KnowledgeRouter().classify(
        message="Explain recursion in simple terms.",
        has_attached_files=False,
        is_follow_up=False,
    )
    assert decision.route is KnowledgeRoute.GENERAL
    assert CeaserOrchestrator._should_run_live_research(
        route=decision.route,
        has_internal_context=False,
    ) is False


def test_explicit_fresh_request_keeps_web_route() -> None:
    decision = KnowledgeRouter().classify(
        message="Search the web for the latest NVIDIA news.",
        has_attached_files=False,
        is_follow_up=False,
    )
    assert decision.route is KnowledgeRoute.RESEARCH


def test_dataset_lookup_is_explicit_only() -> None:
    assert CeaserOrchestrator._should_use_dataset(
        "Explain database normalization.", KnowledgeRoute.GENERAL
    ) is False
    assert CeaserOrchestrator._should_use_dataset(
        "Find a training dataset for sentiment analysis.", KnowledgeRoute.RESEARCH
    ) is True


def test_model_router_reuses_provider_adapter() -> None:
    created: list[object] = []

    def factory() -> object:
        provider = object()
        created.append(provider)
        return provider

    registry = ModelRegistry()
    request = ModelRequest(
        request_id="ttft-provider-cache",
        agent_id="ceaser",
        task_type="general",
        workload=Workload.NORMAL_CHAT,
        policy=RoutingPolicy.BALANCED,
    )
    router = ModelRouter(registry=registry, provider_factories={"openai": factory})
    first = router.model_candidates(request, max_count=1)
    second = router.model_candidates(request, max_count=1)

    assert first and second
    assert first[0][1] is second[0][1]
    assert len(created) == 1
