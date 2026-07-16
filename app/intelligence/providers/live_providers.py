from __future__ import annotations

import re

from app.intelligence.knowledge.models import ContextItem, ContextKind
from app.intelligence.orchestrator.models import ProviderPlan, RequestContext
from app.intelligence.providers.base import KnowledgeProvider
from app.services.news import NewsService
from app.services.weather.openweather_provider import OpenWeatherProvider


class NewsKnowledgeProvider(KnowledgeProvider):
    name = "news"

    async def retrieve(self, *, request: RequestContext, plan: ProviderPlan) -> list[ContextItem]:
        try:
            brief = NewsService().for_automation(name=plan.query, prompt=plan.query)
        except Exception:
            return []
        return [
            ContextItem(
                id=article.url or f"news-{index}",
                provider=self.name,
                kind=ContextKind.NEWS,
                title=article.title,
                content="\n".join(filter(None, [article.title, article.summary, article.source, article.published_at])),
                source_uri=article.url,
                relevance_score=0.75,
                metadata=article.model_dump(),
                permissions=["read"],
            )
            for index, article in enumerate(brief.articles[: plan.limit])
        ]


class WeatherKnowledgeProvider(KnowledgeProvider):
    name = "weather"

    async def retrieve(self, *, request: RequestContext, plan: ProviderPlan) -> list[ContextItem]:
        location = self._location(plan.query) or "Hyderabad, IN"
        report = OpenWeatherProvider().current(location)
        if report.error:
            return []
        content = (
            f"Location: {report.location}\n"
            f"Temperature: {report.temperature} C\n"
            f"Condition: {report.condition}\n"
            f"Humidity: {report.humidity}%\n"
            f"Wind: {report.wind_speed}"
        )
        return [
            ContextItem(
                id=f"weather-{report.location}",
                provider=self.name,
                kind=ContextKind.WEATHER,
                title=f"Weather for {report.location}",
                content=content,
                relevance_score=0.9,
                metadata=report.model_dump(),
                permissions=["read"],
            )
        ]

    def _location(self, query: str) -> str | None:
        match = re.search(r"\b(?:in|at|for)\s+([A-Za-z][A-Za-z .,-]+)$", query.strip(), flags=re.I)
        return match.group(1).strip(" ?.") if match else None

