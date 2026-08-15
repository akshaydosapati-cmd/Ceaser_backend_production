from __future__ import annotations

import json
import re
from uuid import uuid4

from sqlalchemy.orm import Session

from app.agents.v2.orchestrator import AgentOrchestrator
from app.execution.placement import ExecutionPlacementEngine, ExecutionRequest, PlacementPolicy
from app.intelligence.ai.model_router.request_builder import request_for_agent
from app.intelligence.ai.sync import generate_text_sync
from app.models.user import User
from app.services.audit_service import AuditService
from app.services.device_gateway_service import DeviceGatewayService
from app.services.persistent_device_executor import PersistentDeviceExecutor
from app.services.sandbox.models import BoltCodingPlan
from app.core.config.settings import settings


class LocalBoltDispatcher:
    """Backend-owned Bolt planning with execution delegated through the Stage 24.5 gateway."""

    def __init__(self, db: Session):
        self.db = db
        self.gateway = DeviceGatewayService(db)

    def dispatch(self, user: User, prompt: str, *, task_id: str | None = None, project_context: dict | None = None):
        task_id = task_id or f"bolt_{uuid4().hex}"
        self._event(user.id, "bolt.selected", task_id, project_context or {})
        self._event(user.id, "bolt.planning", task_id, project_context or {})
        plan = self._plan(prompt, task_id, project_context or {})
        self._event(user.id, "bolt.plan_ready", task_id, project_context or {}, {"operation_count": len(plan.file_operations)})
        capability = "bolt.execute_plan"
        devices = self.gateway.availability(user.id, capability, preferred_device_id=(project_context or {}).get("device_id"))
        request = ExecutionRequest(
            request_id=f"local_{uuid4().hex}", task_id=task_id, agent_id="bolt", capability=capability,
            arguments={
                "prompt": prompt, "project_name": self._project_name(prompt, project_context),
                "project_id": (project_context or {}).get("project_id"), "coding_plan": plan.model_dump(mode="json"),
                "max_repair_attempts": settings.bolt_max_repair_attempts,
            },
            required_target="DEVICE", user_id=user.id, timeout_seconds=300,
            metadata={"workload": "software_engineering", "local_first": True},
        )
        decision = ExecutionPlacementEngine().place(request, devices=devices, policy=PlacementPolicy.LOCAL_FIRST)
        if not decision.can_execute_now:
            self._event(user.id, "device.waiting", task_id, project_context or {}, {"category": decision.failure.value if decision.failure else "device_required"})
            return {"status": "waiting_for_device", "reason": decision.reason, "failure": decision.failure.value if decision.failure else None, "task_id": task_id}
        command = PersistentDeviceExecutor(self.gateway, user).submit(request, decision)
        return {"status": "queued", "request_id": command.request_id, "task_id": task_id, "device_id": command.device_id, "project_name": request.arguments["project_name"]}

    def _event(self, user_id: str, action: str, task_id: str, project: dict, metadata: dict | None = None) -> None:
        AuditService(self.db).record(
            user_id=user_id,
            action=action,
            resource_type="bolt_project",
            resource_id=project.get("project_id") or task_id,
            metadata={
                "task_id": task_id,
                "project_id": project.get("project_id"),
                "agent_id": "bolt",
                **(metadata or {}),
            },
        )

    def _plan(self, prompt: str, task_id: str, project_context: dict) -> BoltCodingPlan:
        definition = AgentOrchestrator().registry.get("bolt")
        context = AgentOrchestrator().context_builder.build(definition, prompt, {
            "task_id": task_id, "active_project": project_context,
            "execution_environment": {"target": "DEVICE", "local_first": True},
        })
        response = generate_text_sync(
            instructions=(
                f"{definition.instructions}\nReturn JSON only with summary, file_operations, setup_commands, build_commands, test_commands. "
                "Use structured argv arrays, project-relative paths, and no secrets or host paths. Include a real build command. "
                "For an existing project, inspect and minimally modify it. Do not emit shell strings. "
                f"Bounded context: {context}"
            ),
            input_text=prompt, max_output_tokens=6000,
            model_request=request_for_agent("bolt", context_size_estimate=max(1, len(prompt) // 4)),
        )
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", str(response).strip(), flags=re.I)
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end < start:
            raise ValueError("invalid_coding_plan")
        return BoltCodingPlan.model_validate(json.loads(text[start:end + 1]))

    @staticmethod
    def _project_name(prompt: str, context: dict) -> str:
        if context.get("display_name"):
            return str(context["display_name"])
        text = re.sub(r"\b(build|create|develop|make|add|implement|please|me|a|an|modern|new)\b", " ", prompt, flags=re.I)
        text = re.sub(r"\b(website|site|application|app|project)\b.*$", " project", text, flags=re.I)
        clean = " ".join(text.split()).strip(" .")
        return (clean or "CEASER Project")[:120].title()
