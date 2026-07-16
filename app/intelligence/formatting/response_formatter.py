from __future__ import annotations

from typing import Any

from app.intelligence.knowledge.models import ContextPackage
from app.intelligence.orchestrator.models import IntentType


class ResponseFormatter:
    def format(self, *, intent: IntentType, domain_result: Any, context: ContextPackage) -> dict:
        return {
            "intent": intent.value,
            "result": domain_result,
            "sources": [
                {
                    "id": item.source_id or item.id,
                    "title": item.title,
                    "kind": item.kind.value,
                    "provider": item.provider,
                }
                for item in context.items
            ],
        }


response_formatter = ResponseFormatter()

