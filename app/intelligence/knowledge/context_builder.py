from __future__ import annotations

from app.intelligence.knowledge.models import ContextItem, ContextPackage
from app.intelligence.orchestrator.models import RequestContext


class ContextBuilder:
    def build(self, *, request: RequestContext, items: list[ContextItem], token_budget: int = 6000) -> ContextPackage:
        sorted_items = sorted(
            items,
            key=lambda item: (item.relevance_score, item.freshness_score, item.authority_score),
            reverse=True,
        )
        deduped: list[ContextItem] = []
        seen_keys: set[tuple[str, str | None]] = set()
        for item in sorted_items:
            key = (item.provider, item.source_id or item.id)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            deduped.append(item)
        lines: list[str] = []
        used = 0
        for index, item in enumerate(deduped[:12], start=1):
            text = item.content.strip()
            estimated_tokens = max(1, len(text) // 4)
            if len(text) > 1800:
                text = text[:1800].rstrip() + "..."
            if used + estimated_tokens > token_budget:
                break
            title = item.title or item.kind.value
            provenance = f"{item.provider}:{item.kind.value}"
            if item.source_id and item.source_id != item.id:
                provenance = f"{provenance} ({item.source_id})"
            lines.append(f"[{index}] {provenance} - {title}\n{text}")
            used += estimated_tokens
        return ContextPackage(items=deduped[: len(lines)], evidence_text="\n\n".join(lines), token_budget=token_budget)


context_builder = ContextBuilder()
