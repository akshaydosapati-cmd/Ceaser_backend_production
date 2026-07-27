from __future__ import annotations

import re

from app.intelligence.orchestrator.models import IntentType, ProviderPlan, RequestContext, RetrievalPlan


class RetrievalPlanner:
    async def build(self, *, request: RequestContext, intent: IntentType) -> RetrievalPlan:
        query = request.message
        if intent == IntentType.GENERAL_QUESTION:
            scope = self._general_question_scope(request)
            providers: list[ProviderPlan] = []
            if scope == "conversation_only":
                providers.append(ProviderPlan(provider="conversation", query=query, limit=4))
            return RetrievalPlan(
                intent=intent,
                providers=providers,
                needs_generation=True,
                output_format="chat",
                retrieval_scope=scope,
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
                retrieval_scope="integrations",
            )
        if intent in {IntentType.FILE_SUMMARY, IntentType.DOCUMENT_GENERATION, IntentType.PROJECT_QUESTION, IntentType.MEMORY_QUESTION}:
            scope = "memory" if intent == IntentType.MEMORY_QUESTION else "project" if intent == IntentType.PROJECT_QUESTION else "file_rag"
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
                retrieval_scope=scope,
            )
        if intent == IntentType.RESEARCH:
            query_lower = query.lower()
            live_provider = "weather" if any(term in query_lower for term in ["weather", "temperature", "rain", "forecast"]) else "news" if "news" in query_lower or "latest" in query_lower else "documents"
            is_current_web_query = live_provider == "news" and not request.project_id and not any(term in query_lower for term in ["project", "my ", "our ", "document", "file", "draft", "workflow"])
            if is_current_web_query:
                providers = [ProviderPlan(provider="news", query=query, required=True, limit=8)]
            else:
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
                retrieval_scope="web" if live_provider in {"weather", "news"} else "mixed",
            )
        if intent == IntentType.FILE_LOOKUP:
            return RetrievalPlan(
                intent=intent,
                providers=[ProviderPlan(provider="files", query=query, required=True, limit=10)],
                needs_generation=False,
                output_format="file_cards",
                retrieval_scope="file_rag",
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
                retrieval_scope="integrations",
            )
        return RetrievalPlan(intent=intent, providers=[], needs_generation=True, output_format="chat", retrieval_scope="mixed")

    def _general_question_scope(self, request: RequestContext) -> str:
        text = request.message.lower().strip()
        if not request.conversation_id:
            return "none"
        follow_up_patterns = (
            r"\b(continue|earlier|previous|before|that|this|it|those|these|what about|more on|go deeper|expand)\b",
            r"^(and|also|then|so)\b",
        )
        return "conversation_only" if any(re.search(pattern, text) for pattern in follow_up_patterns) else "none"


retrieval_planner = RetrievalPlanner()
