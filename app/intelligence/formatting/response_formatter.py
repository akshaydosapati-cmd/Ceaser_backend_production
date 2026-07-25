from __future__ import annotations

from typing import Any

from app.intelligence.knowledge.models import ContextPackage
from app.intelligence.orchestrator.models import IntentType


class ResponseFormatter:
    def format(self, *, intent: IntentType, domain_result: Any, context: ContextPackage) -> dict:
        return {
            "intent": intent.value,
            "format": self._format_for_intent(intent),
            "result": domain_result,
            "sources": self._sources_for_intent(intent, context),
            "summary": self._summary_for_intent(intent, context, domain_result),
        }

    def _format_for_intent(self, intent: IntentType) -> str:
        return {
            IntentType.FILE_LOOKUP: "file_cards",
            IntentType.FILE_SUMMARY: "summary",
            IntentType.PROJECT_QUESTION: "project_brief",
            IntentType.MEMORY_QUESTION: "memory_brief",
            IntentType.DOCUMENT_GENERATION: "document",
            IntentType.RESEARCH: "research_report",
            IntentType.EMAIL_DRAFT: "email_preview",
            IntentType.CALENDAR_LOOKUP: "calendar_list",
            IntentType.CALENDAR_CREATE: "calendar_action",
            IntentType.DESKTOP_ACTION: "desktop_confirmation",
            IntentType.WORKFLOW: "workflow_report",
        }.get(intent, "chat")

    def _sources_for_intent(self, intent: IntentType, context: ContextPackage) -> list[dict[str, Any]]:
        if intent in {IntentType.DESKTOP_ACTION, IntentType.CALENDAR_CREATE}:
            return []
        sources = []
        for item in context.items[:8]:
            sources.append(
                {
                    "id": item.source_id or item.id,
                    "title": item.title,
                    "kind": item.kind.value,
                    "provider": item.provider,
                    "freshness_score": item.freshness_score,
                    "authority_score": item.authority_score,
                }
            )
        return sources

    def _summary_for_intent(self, intent: IntentType, context: ContextPackage, domain_result: Any) -> str:
        count = len(context.items)
        if intent == IntentType.DESKTOP_ACTION:
            return "Desktop action classified and routed."
        if intent == IntentType.CALENDAR_LOOKUP:
            return f"Calendar lookup completed with {count} relevant items."
        if intent == IntentType.FILE_LOOKUP:
            return f"Found {count} file matches."
        if intent == IntentType.RESEARCH:
            return f"Research assembled from {count} ranked context items."
        if intent == IntentType.DOCUMENT_GENERATION:
            return f"Document draft prepared using {count} context items."
        if isinstance(domain_result, str):
            return domain_result[:240]
        return f"Formatted {intent.value} response with {count} context items."


response_formatter = ResponseFormatter()
