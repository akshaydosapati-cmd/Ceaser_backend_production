from __future__ import annotations

from urllib.parse import urlparse

from app.engines.research_engine.schemas import ResearchSource
from app.engines.research_engine.search_provider import DuckDuckGoSearchProvider, SearchProvider


class SourceCollector:
    def __init__(self, provider: SearchProvider | None = None):
        self.provider = provider or DuckDuckGoSearchProvider()

    def collect_sources(self, query: str, limit: int = 6) -> list[ResearchSource]:
        raw_sources = self.provider.search(query=query, limit=limit * 2)
        deduped: dict[str, ResearchSource] = {}
        for raw in raw_sources:
            url = raw.get("url", "")
            if not url or url in deduped:
                continue
            source = ResearchSource(
                title=raw.get("title") or url,
                url=url,
                source=raw.get("source") or self._host(url),
                snippet=raw.get("snippet") or "",
                score=self._score(query=query, title=raw.get("title", ""), snippet=raw.get("snippet", ""), url=url),
            )
            deduped[url] = source
        return sorted(deduped.values(), key=lambda item: item.score, reverse=True)[:limit]

    def _score(self, query: str, title: str, snippet: str, url: str) -> float:
        query_terms = {term.lower() for term in query.split() if len(term) > 2}
        content = f"{title} {snippet}".lower()
        relevance = sum(1 for term in query_terms if term in content) * 3
        authority = 2 if any(domain in url for domain in ["who.int", "nih.gov", "gov", "edu", "wikipedia.org"]) else 1
        freshness = 1 if any(term in content for term in ["2026", "2025", "latest", "recent"]) else 0
        return relevance + authority + freshness

    def _host(self, url: str) -> str:
        return urlparse(url).netloc.replace("www.", "")
