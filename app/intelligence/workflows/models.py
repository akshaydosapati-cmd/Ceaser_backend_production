from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class WorkflowStepPlan:
    name: str
    kind: str
    payload: dict[str, Any] = field(default_factory=dict)
    requires_confirmation: bool = False


@dataclass(slots=True)
class WorkflowPlan:
    workflow_type: str
    steps: list[WorkflowStepPlan]
    output_format: str

