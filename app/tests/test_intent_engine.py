from app.intelligence.orchestrator.intent_engine import IntentEngine
from app.intelligence.orchestrator.models import IntentType, RequestContext


async def _classify(message: str):
    request = RequestContext(user_id="test-user", message=message)
    intent = await IntentEngine().classify(request)
    return intent, request.metadata


def test_intent_engine_sets_cloud_comparison_metadata() -> None:
    import asyncio

    intent, metadata = asyncio.run(_classify("Compare AWS and Azure for startup infrastructure"))
    assert intent == IntentType.RESEARCH
    assert metadata["intent_domain"] == "technology"
    assert metadata["intent_subdomain"] == "cloud_comparison"


def test_intent_engine_sets_branding_metadata() -> None:
    import asyncio

    intent, metadata = asyncio.run(_classify("Design a logo for CEASER"))
    assert intent == IntentType.DOCUMENT_GENERATION
    assert metadata["intent_domain"] == "creative"
    assert metadata["intent_subdomain"] == "branding_design"


def test_intent_engine_sets_finance_tax_metadata() -> None:
    import asyncio

    intent, metadata = asyncio.run(_classify("Explain GST in India"))
    assert intent == IntentType.GENERAL_QUESTION
    assert metadata["intent_domain"] == "finance"
    assert metadata["intent_subdomain"] == "taxation"
