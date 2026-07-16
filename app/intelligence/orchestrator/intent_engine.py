from __future__ import annotations

from app.intelligence.orchestrator.models import IntentType, RequestContext


class IntentEngine:
    async def classify(self, request: RequestContext) -> IntentType:
        text = request.message.lower().strip()
        if any(term in text for term in ["calendar", "event", "meeting", "schedule today", "tomorrow"]):
            return IntentType.CALENDAR_LOOKUP
        if any(term in text for term in ["weather", "temperature", "rain", "forecast"]):
            return IntentType.RESEARCH
        if any(term in text for term in ["summarize this file", "summarize the file", "summarize pdf", "summarize document"]):
            return IntentType.FILE_SUMMARY
        if any(term in text for term in ["find file", "open file", "latest pdf", "in downloads", "in documents"]):
            return IntentType.FILE_LOOKUP
        if any(term in text for term in ["create document", "create a document", "make pdf", "write document", "generate document"]):
            return IntentType.DOCUMENT_GENERATION
        if any(term in text for term in ["research", "latest", "news", "sources", "market", "competitor"]):
            return IntentType.RESEARCH
        if any(term in text for term in ["email", "gmail", "send mail", "draft mail"]):
            return IntentType.EMAIL_DRAFT
        if request.project_id or "project" in text:
            return IntentType.PROJECT_QUESTION
        if any(term in text for term in ["remember", "memory", "what is my name", "who am i"]):
            return IntentType.MEMORY_QUESTION
        return IntentType.GENERAL_QUESTION


intent_engine = IntentEngine()
