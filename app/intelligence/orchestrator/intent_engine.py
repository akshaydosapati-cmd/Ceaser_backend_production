from __future__ import annotations

import re

from app.intelligence.orchestrator.models import IntentType, RequestContext


class IntentEngine:
    async def classify(self, request: RequestContext) -> IntentType:
        text = request.message.lower().strip()
        domain, subdomain = self._classify_domain(text)
        request.metadata["intent_domain"] = domain
        request.metadata["intent_subdomain"] = subdomain
        if self._looks_like_desktop_action(text):
            return IntentType.DESKTOP_ACTION
        if any(term in text for term in ["what did we decide", "what did we decide about", "previous conversation", "previous chat", "last time we discussed", "what is my name", "who am i", "remember", "memory"]):
            return IntentType.MEMORY_QUESTION
        if any(term in text for term in ["calendar", "event", "meeting", "schedule today", "tomorrow"]):
            return IntentType.CALENDAR_LOOKUP
        if any(term in text for term in ["weather", "temperature", "rain", "forecast"]):
            return IntentType.RESEARCH
        if any(term in text for term in ["summarize this file", "summarize the file", "summarize pdf", "summarize document", "uploaded document", "uploaded file", "this pdf", "this document"]):
            return IntentType.FILE_SUMMARY
        if any(term in text for term in ["find file", "open file", "latest pdf", "in downloads", "in documents"]):
            return IntentType.FILE_LOOKUP
        if any(term in text for term in ["create document", "create a document", "make pdf", "write document", "generate document", "design a logo", "create logo", "make a logo", "presentation outline", "create presentation", "generate interview questions"]):
            return IntentType.DOCUMENT_GENERATION
        if any(term in text for term in ["research", "latest", "news", "sources", "market", "competitor", "compare aws", "compare azure", "compare cloud", "aws and azure"]):
            return IntentType.RESEARCH
        if any(term in text for term in ["email", "gmail", "send mail", "draft mail"]):
            return IntentType.EMAIL_DRAFT
        if request.project_id or "project" in text:
            return IntentType.PROJECT_QUESTION
        return IntentType.GENERAL_QUESTION

    def _classify_domain(self, text: str) -> tuple[str, str]:
        if any(term in text for term in ["aws", "azure", "gcp", "cloud computing", "kubernetes", "docker"]):
            if "compare" in text or "vs" in text or "versus" in text:
                return "technology", "cloud_comparison"
            return "technology", "cloud_platforms"
        if any(term in text for term in ["logo", "branding", "brand identity", "color palette", "typography"]):
            return "creative", "branding_design"
        if any(term in text for term in ["interview", "mock interview", "hr round", "technical round", "behavioral questions"]):
            return "career", "interview_preparation"
        if any(term in text for term in ["gst", "tax", "taxation", "indirect tax", "budget", "finance", "financial"]):
            return "finance", "taxation" if any(term in text for term in ["gst", "tax", "taxation", "indirect tax"]) else "financial_planning"
        if any(term in text for term in ["trip", "travel", "itinerary", "flight", "hotel", "visa", "destination"]):
            return "travel", "trip_planning"
        if any(term in text for term in ["ramayana", "mahabharata", "krishna", "mythology", "epic", "character"]):
            return "knowledge", "mythology"
        if any(term in text for term in ["black hole", "quantum", "physics", "science"]):
            return "knowledge", "science"
        if any(term in text for term in ["python", "react", "javascript", "bug", "debug", "algorithm", "api", "code"]):
            return "creation", "coding"
        if any(term in text for term in ["startup", "marketing", "sales", "strategy", "competitor"]):
            return "business", "strategy"
        if any(term in text for term in ["email", "presentation", "slides", "document", "report", "outline"]):
            return "creation", "writing"
        return "general", "general"

    def _looks_like_desktop_action(self, text: str) -> bool:
        if any(term in text for term in ["open chrome", "open edge", "open vscode", "open vs code", "open file explorer", "open downloads", "pause music", "resume music", "take screenshot", "clipboard"]):
            return True
        return bool(re.search(r"\b(open|launch|start|pause|resume|play|search|find|show)\b", text) and re.search(r"\b(chrome|edge|vscode|vs code|downloads|documents|music|song|screenshot|clipboard|notepad|calculator)\b", text))


intent_engine = IntentEngine()
