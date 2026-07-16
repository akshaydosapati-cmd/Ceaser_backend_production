from __future__ import annotations

from app.intelligence.orchestrator.models import IntentType, ProviderPlan, RequestContext, RetrievalPlan


class RetrievalPlanner:
    async def build(self, *, request: RequestContext, intent: IntentType) -> RetrievalPlan:
        query = request.message
        if intent == IntentType.GENERAL_QUESTION:
            return RetrievalPlan(
                intent=intent,
                providers=[
                    ProviderPlan(provider="conversation", query=query, limit=6),
                    ProviderPlan(provider="memory", query=query, limit=5),
                ],
                needs_generation=True,
                output_format="chat",
            )
        if intent == IntentType.CALENDAR_LOOKUP:
            return RetrievalPlan(
                intent=intent,
                providers=[
                    ProviderPlan(provider="calendar", query=query, required=True, limit=10),
                    ProviderPlan(provider="conversation", query=query, limit=3),
                ],
                needs_generation=False,
                output_format="calendar_events",
            )
        if intent in {IntentType.FILE_SUMMARY, IntentType.DOCUMENT_GENERATION, IntentType.PROJECT_QUESTION, IntentType.MEMORY_QUESTION}:
            return RetrievalPlan(
                intent=intent,
                providers=[
                    ProviderPlan(provider="projects", query=query, filters={"project_id": request.project_id}, limit=3),
                    ProviderPlan(provider="memory", query=query, limit=5),
                    ProviderPlan(
                        provider="documents",
                        query=query,
                        filters={"project_id": request.project_id, "source_id": request.source_id},
                        limit=8,
                    )
                ],
                needs_generation=True,
                output_format="document" if intent == IntentType.DOCUMENT_GENERATION else "chat",
            )
        if intent == IntentType.RESEARCH:
            live_provider = "weather" if any(term in query.lower() for term in ["weather", "temperature", "rain", "forecast"]) else "news" if "news" in query.lower() or "latest" in query.lower() else "documents"
            providers = [
                ProviderPlan(provider="projects", query=query, filters={"project_id": request.project_id}, limit=3),
                ProviderPlan(provider="generated_artifacts", query=query, filters={"project_id": request.project_id}, limit=4),
                ProviderPlan(provider="documents", query=query, filters={"project_id": request.project_id}, limit=5),
            ]
            if live_provider in {"weather", "news"}:
                providers.insert(0, ProviderPlan(provider=live_provider, query=query, required=True, limit=8))
            return RetrievalPlan(
                intent=intent,
                providers=providers,
                needs_generation=True,
                output_format="research_report",
            )
        if intent == IntentType.FILE_LOOKUP:
            return RetrievalPlan(
                intent=intent,
                providers=[ProviderPlan(provider="files", query=query, required=True, limit=10)],
                needs_generation=False,
                output_format="file_cards",
            )
        if intent == IntentType.EMAIL_DRAFT:
            return RetrievalPlan(
                intent=intent,
                providers=[
                    ProviderPlan(provider="gmail", query=query, required=False, limit=5),
                    ProviderPlan(provider="memory", query=query, limit=5),
                    ProviderPlan(provider="documents", query=query, filters={"project_id": request.project_id}, limit=5),
                ],
                needs_generation=True,
                output_format="email_preview",
                requires_confirmation=True,
            )
        return RetrievalPlan(intent=intent, providers=[], needs_generation=True, output_format="chat")


retrieval_planner = RetrievalPlanner()
