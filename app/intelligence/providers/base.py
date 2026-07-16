from __future__ import annotations

from abc import ABC, abstractmethod

from app.intelligence.knowledge.models import ContextItem
from app.intelligence.orchestrator.models import ProviderPlan, RequestContext


class KnowledgeProvider(ABC):
    name: str

    @abstractmethod
    async def retrieve(self, *, request: RequestContext, plan: ProviderPlan) -> list[ContextItem]:
        raise NotImplementedError

