from __future__ import annotations

from sqlalchemy.orm import Session

from app.intelligence.knowledge.models import ContextItem, ContextKind
from app.intelligence.orchestrator.models import ProviderPlan, RequestContext
from app.intelligence.providers.base import KnowledgeProvider
from app.services.integrations import IntegrationManager


class IntegrationKnowledgeProvider(KnowledgeProvider):
    def __init__(self, db: Session, *, name: str, provider_id: str, kind: ContextKind) -> None:
        self.db = db
        self.name = name
        self.provider_id = provider_id
        self.kind = kind

    async def retrieve(self, *, request: RequestContext, plan: ProviderPlan) -> list[ContextItem]:
        manager = IntegrationManager(self.db)
        try:
            manager.sync_if_stale(user_id=request.user_id, provider_id=self.provider_id, max_age_seconds=300)
            metadata = manager.metadata(user_id=request.user_id, provider_id=self.provider_id)
        except Exception:
            return []
        if metadata.get("status") != "connected":
            return []
        items = metadata.get("items") or []
        results: list[ContextItem] = []
        for index, item in enumerate(items[: plan.limit]):
            title = item.get("title") or item.get("subject") or item.get("name") or item.get("course_title") or f"{self.name} item"
            content = self._content(item)
            results.append(
                ContextItem(
                    id=str(item.get("id") or f"{self.provider_id}-{index}"),
                    provider=self.name,
                    kind=self.kind,
                    title=title,
                    content=content,
                    source_uri=item.get("url") or item.get("html_link"),
                    relevance_score=0.7,
                    metadata=item,
                    permissions=["read"],
                )
            )
        return results

    def _content(self, item: dict) -> str:
        lines = []
        for key in ("title", "subject", "name", "summary", "snippet", "from", "start", "end", "due", "modified_time", "status"):
            value = item.get(key)
            if value:
                lines.append(f"{key}: {value}")
        return "\n".join(lines) or str(item)
