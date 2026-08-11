from __future__ import annotations

from urllib.parse import urlparse

from app.engines.research_engine.page_extractor import PageExtractor
from app.engines.research_engine.schemas import ResearchSource
from app.engines.research_engine.search_provider import GoogleSearchProvider, SearchProvider


class SourceCollector:
    def __init__(self, provider: SearchProvider | None = None, page_extractor: PageExtractor | None = None):
        self.provider = provider or GoogleSearchProvider()
        self.page_extractor = page_extractor or PageExtractor()

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
                image_url=raw.get("image_url"),
                score=self._score(query=query, title=raw.get("title", ""), snippet=raw.get("snippet", ""), url=url),
            )
            deduped[url] = source
        ranked_sources = sorted(deduped.values(), key=lambda item: item.score, reverse=True)[:limit]
        for source in ranked_sources:
            extracted = self.page_extractor.extract(source.url, query)
            if not extracted:
                continue
            source.excerpt = extracted.excerpt
            source.publisher = extracted.publisher
            source.retrieved_at = extracted.retrieved_at
            source.image_url = source.image_url or extracted.image_url
            if extracted.title and (not source.title or source.title == source.url):
                source.title = extracted.title
            if extracted.excerpt:
                source.snippet = extracted.excerpt[:500]
                source.score += 2
        return sorted(ranked_sources, key=lambda item: item.score, reverse=True)

    def _score(self, query: str, title: str, snippet: str, url: str) -> float:
        query_terms = {term.lower() for term in query.split() if len(term) > 2}
        content = f"{title} {snippet}".lower()
        relevance = sum(1 for term in query_terms if term in content) * 3
        authority = 2 if any(domain in url for domain in ["who.int", "nih.gov", "gov", "edu", "wikipedia.org"]) else 1
        freshness = 1 if any(term in content for term in ["2026", "2025", "latest", "recent"]) else 0
        return relevance + authority + freshness

    def _host(self, url: str) -> str:
        return urlparse(url).netloc.replace("www.", "")
