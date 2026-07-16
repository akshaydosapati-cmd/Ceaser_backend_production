from __future__ import annotations

from abc import ABC, abstractmethod

from app.intelligence.actions.models import ActionResult, PlannedAction


class ActionProvider(ABC):
    name: str

    @abstractmethod
    async def validate(self, action: PlannedAction) -> None:
        raise NotImplementedError

    @abstractmethod
    async def execute(self, action: PlannedAction) -> ActionResult:
        raise NotImplementedError

