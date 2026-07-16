from __future__ import annotations

from app.intelligence.actions.base import ActionProvider
from app.intelligence.actions.models import ActionResult, PlannedAction


class ActionEngine:
    def __init__(self, providers: dict[str, ActionProvider] | None = None) -> None:
        self.providers = providers or {}

    async def execute(self, action: PlannedAction, *, approved: bool = False) -> ActionResult:
        if action.requires_confirmation and not approved:
            return ActionResult(
                action_type=action.action_type,
                provider=action.provider,
                status="needs_confirmation",
                message="Approval is required before CEASER performs this action.",
            )
        provider = self.providers.get(action.provider)
        if not provider:
            return ActionResult(
                action_type=action.action_type,
                provider=action.provider,
                status="unsupported",
                message="This action provider is not connected yet.",
            )
        await provider.validate(action)
        return await provider.execute(action)

