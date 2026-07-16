from __future__ import annotations

from app.intelligence.knowledge.models import ContextItem, ContextPackage
from app.intelligence.orchestrator.models import RequestContext


class ContextBuilder:
    def build(self, *, request: RequestContext, items: list[ContextItem], token_budget: int = 6000) -> ContextPackage:
        sorted_items = sorted(items, key=lambda item: item.relevance_score, reverse=True)
        lines: list[str] = []
        used = 0
        for index, item in enumerate(sorted_items, start=1):
            text = item.content.strip()
            estimated_tokens = max(1, len(text) // 4)
            if used + estimated_tokens > token_budget:
                break
            title = item.title or item.kind.value
            lines.append(f"[{index}] {item.provider}:{item.kind.value} - {title}\n{text}")
            used += estimated_tokens
        return ContextPackage(items=sorted_items[: len(lines)], evidence_text="\n\n".join(lines), token_budget=token_budget)


context_builder = ContextBuilder()

