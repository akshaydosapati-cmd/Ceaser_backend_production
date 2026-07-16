from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class PlannedAction:
    action_type: str
    provider: str
    payload: dict[str, Any] = field(default_factory=dict)
    requires_confirmation: bool = True


@dataclass(slots=True)
class ActionResult:
    action_type: str
    provider: str
    status: str
    message: str
    data: dict[str, Any] = field(default_factory=dict)

