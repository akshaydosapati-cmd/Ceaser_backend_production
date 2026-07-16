from __future__ import annotations

from sqlalchemy.orm import Session

from app.intelligence.providers.base import KnowledgeProvider
from app.intelligence.providers.document_provider import DocumentKnowledgeProvider


class KnowledgeProviderRegistry:
    def __init__(self, db: Session) -> None:
        self.providers: dict[str, KnowledgeProvider] = {
            "documents": DocumentKnowledgeProvider(db),
        }

    def get(self, name: str) -> KnowledgeProvider | None:
        return self.providers.get(name)

