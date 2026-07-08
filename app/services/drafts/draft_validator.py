from __future__ import annotations

from app.services.drafts.draft_schema_registry import DraftSchemaRegistry


class DraftValidationError(ValueError):
    pass


class DraftValidator:
    def validate(self, content: dict, draft_type: str) -> dict:
        if not isinstance(content, dict):
            raise DraftValidationError("Draft content must be a JSON object.")
        if content.get("draft_type") != draft_type:
            raise DraftValidationError("Draft type does not match schema.")
        serialized = str(content)
        banned = [
            "Draft point for",
            " point for ",
            "placeholder",
            "Needs review before desktop execution",
            "template text",
            "TBD",
            "Clarify the ",
            "Connect the work to the user's current CEASER context",
            "Identify the highest-impact action",
            "Convert the insight into a concrete next step",
            "Review the executive summary assumptions",
            "Review the problem assumptions",
            "Review the solution assumptions",
            "Review the market assumptions",
            "Review the business model assumptions",
            "Review the go-to-market assumptions",
            "Review the financial plan assumptions",
            "Explain the title clearly",
            "Explain the problem clearly",
            "Explain the solution clearly",
            "Explain the market clearly",
            "Talk through why",
            "Use a clean visual that shows",
            "needs a clear owner",
            "move this work toward",
            "next decision",
            "internal planning",
        ]
        if any(term.lower() in serialized.lower() for term in banned):
            raise DraftValidationError("Generic placeholder draft content is not allowed.")
        schema = DraftSchemaRegistry().get(draft_type)
        for key in schema:
            if key not in content:
                raise DraftValidationError(f"Missing required field: {key}")
        return content
