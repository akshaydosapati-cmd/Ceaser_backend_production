from __future__ import annotations

import re

from app.services.drafts.schemas import DraftContent
from app.services.drafts.structured_draft_generator import StructuredDraftGenerator


class DraftGenerator:
    def generate(self, *, prompt: str, draft_type: str, agent_id: str, title: str | None = None, target_app: str = "keep_as_draft", requested_units: int = 8, context: dict | None = None) -> DraftContent:
        title = title or self._title(prompt, draft_type)
        structured = StructuredDraftGenerator().generate(prompt=prompt, draft_type=draft_type, agent_id=agent_id, title=title, target_app=target_app, requested_units=requested_units, context=context or {})
        payload = {"title": title, "type": draft_type, "owner_agent": agent_id, **structured}
        payload.setdefault("sections", [])
        return DraftContent(**payload)

    @staticmethod
    def _title(prompt: str, draft_type: str) -> str:
        cleaned = re.sub(r"\b(create|generate|make|a|an|the|draft|plan|deck|for|with)\b", " ", prompt, flags=re.I)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
        return (cleaned.title() if cleaned else draft_type.replace("_", " ").title())[:100]
