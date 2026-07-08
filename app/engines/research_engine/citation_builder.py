from __future__ import annotations

from app.engines.research_engine.schemas import Citation, ResearchSource


class CitationBuilder:
    def build(self, sources: list[ResearchSource]) -> list[Citation]:
        return [Citation(title=source.title, url=source.url) for source in sources]
