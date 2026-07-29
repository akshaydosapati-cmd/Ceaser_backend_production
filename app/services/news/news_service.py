from __future__ import annotations

import re

from app.core.config.settings import settings
from app.services.news.newsapi_provider import NewsApiProvider
from app.services.news.rapidapi_google_news_provider import RapidApiGoogleNewsProvider
from app.services.news.schemas import NewsBrief


class NewsService:
    def __init__(self, provider: NewsApiProvider | RapidApiGoogleNewsProvider | None = None):
        self.provider = provider or self._provider()

    def _provider(self) -> NewsApiProvider | RapidApiGoogleNewsProvider:
        configured = (settings.news_provider or "").lower().strip()
        if configured in {"rapidapi", "rapidapi_google_news", "google-news13"}:
            return RapidApiGoogleNewsProvider()
        if configured in {"newsapi", "newsapi.org"}:
            return NewsApiProvider()
        if settings.news_api_key:
            return NewsApiProvider()
        return RapidApiGoogleNewsProvider()

    def for_automation(self, *, name: str, prompt: str | None = None) -> NewsBrief:
        text = f"{name} {prompt or ''}".lower()
        if any(term in text for term in ["healthtech", "health tech", "digital health", "healthcare", "medical"]):
            return self.provider.search("latest healthtech news")
        if any(term in text for term in ["startup", "funding", "venture", "vc"]):
            return self.provider.search("latest startup funding news")
        if any(term in text for term in ["artificial intelligence", "ai ", " ai", "model", "openai", "gemini"]):
            return self.provider.search("latest artificial intelligence news")
        if "business" in text:
            return self.provider.category("business")
        if any(term in text for term in ["technology", "tech"]):
            return self.provider.category("technology")
        if any(term in text for term in ["daily news reader", "daily news briefing", "top headlines", "general news"]):
            return self.provider.latest()
        query = self._extract_query(prompt or name)
        if query:
            return self.provider.search(query)
        return self.provider.latest()

    def _extract_query(self, value: str) -> str:
        cleaned = re.sub(r"\b(a|an|the|create|daily|weekly|news|reader|digest|brief|briefing|latest|with|top|headlines)\b", " ", value, flags=re.I)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" .,:;")
        return cleaned[:120] if len(cleaned) >= 3 else ""
