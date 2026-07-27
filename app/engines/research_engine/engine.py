from __future__ import annotations

from app.engines.research_engine.citation_builder import CitationBuilder
from app.engines.research_engine.schemas import ResearchResult
from app.engines.research_engine.source_collector import SourceCollector


class ResearchEngine:
    def __init__(self, source_collector: SourceCollector | None = None, citation_builder: CitationBuilder | None = None):
        self.source_collector = source_collector or SourceCollector()
        self.citation_builder = citation_builder or CitationBuilder()

    def research(self, query: str) -> ResearchResult:
        sources = self.source_collector.collect_sources(query=query)
        citations = self.citation_builder.build(sources)
        key_findings = [source.excerpt or source.snippet for source in sources if source.excerpt or source.snippet][:5]
        summary = self._summary(query=query, key_findings=key_findings, source_count=len(sources))
        return ResearchResult(
            query=query,
            summary=summary,
            key_findings=key_findings,
            sources=sources,
            citations=citations,
        )

    def _summary(self, query: str, key_findings: list[str], source_count: int) -> str:
        if not source_count:
            return f"No live sources were found for '{query}'. CEASER can still reason from memory and agent context."
        return f"Collected {source_count} ranked sources for '{query}' and prepared citation-backed research context."
