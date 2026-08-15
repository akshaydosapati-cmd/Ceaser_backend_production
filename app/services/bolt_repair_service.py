from __future__ import annotations

import json
import re
from uuid import uuid4

from sqlalchemy.orm import Session

from app.agents.v2 import DeviceCapabilityRequest
from app.core.config.settings import settings
from app.intelligence.ai.model_router.request_builder import request_for_agent
from app.intelligence.ai.sync import generate_text_sync
from app.models.desktop import DesktopCommand
from app.models.user import User
from app.services.audit_service import AuditService
from app.services.device_gateway_service import DeviceGatewayService
from app.services.sandbox.models import BoltCodingPlan


class BoltRepairService:
    def __init__(self, db: Session):
        self.db = db

    def handle(self, command: DesktopCommand) -> DesktopCommand | None:
        if command.capability != "bolt.execute_plan":
            return None
        output = ((command.result_json or {}).get("output") or {})
        self._record_device_events(command, output)
        if command.status == "COMPLETED" and output.get("verified"):
            return None
        request = command.request_json or {}; metadata = request.get("metadata") or {}; attempt = int(metadata.get("repair_attempt") or 0)
        if attempt >= settings.bolt_max_repair_attempts:
            self._event(command, "bolt.failed", {"attempt": attempt, "category": output.get("error_code") or "verification_failed"})
            return None
        project = output.get("project") or {}; project_id = project.get("project_id")
        if not project_id:
            self._event(command, "bolt.repair_failed", {"attempt": attempt + 1, "category": "project_not_available"})
            return None
        self._event(command, "bolt.repair_started", {"attempt": attempt + 1})
        try:
            plan = self._repair_plan(command, output, attempt + 1)
        except Exception:
            self._event(command, "bolt.repair_failed", {"attempt": attempt + 1, "category": "invalid_repair_plan"})
            return None
        self._event(command, "bolt.repair_plan_ready", {"attempt": attempt + 1, "operation_count": len(plan.file_operations)})
        user = self.db.query(User).filter(User.id == command.user_id).first()
        if not user:
            return None
        follow_up = DeviceCapabilityRequest(
            request_id=f"{command.request_id}:repair:{attempt + 1}:{uuid4().hex[:8]}", task_id=command.task_id,
            agent_id="bolt", device_id=command.device_id, capability="bolt.execute_plan",
            arguments={"project_id": project_id, "project_name": project.get("display_name"), "coding_plan": plan.model_dump(mode="json"), "max_repair_attempts": 0},
            timeout_seconds=300, authorization={"user_id": command.user_id},
            metadata={"workload": "software_engineering", "repair_attempt": attempt + 1, "parent_request_id": command.request_id},
        )
        queued = DeviceGatewayService(self.db).submit(user, follow_up)
        self._event(command, "bolt.repair_applied", {"attempt": attempt + 1, "request_id": queued.request_id})
        return queued

    def _repair_plan(self, command, output, attempt):
        evidence = output.get("evidence") or {}; commands = evidence.get("commands") or []
        safe_context = {
            "project": {"project_id": (output.get("project") or {}).get("project_id"), "framework": (output.get("project") or {}).get("framework"), "language": (output.get("project") or {}).get("language")},
            "failure": {"error_code": output.get("error_code"), "message": str(output.get("message") or "")[:500], "commands": commands[-4:]},
            "changed_files": (evidence.get("files") or [])[-100:], "attempt": attempt,
            "remaining_attempts": max(0, settings.bolt_max_repair_attempts - attempt),
        }
        response = generate_text_sync(
            instructions=("You are Bolt repairing a failed local build. Return JSON only using BoltCodingPlan fields: summary, file_operations, setup_commands, build_commands, test_commands. Use project-relative paths and structured argv only. Never request secrets, .env files, host paths, or arbitrary shell text."),
            input_text=json.dumps(safe_context, ensure_ascii=True), max_output_tokens=5000,
            model_request=request_for_agent("bolt", context_size_estimate=max(1, len(json.dumps(safe_context)) // 4)),
        )
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", str(response).strip(), flags=re.I); start, end = text.find("{"), text.rfind("}")
        if start < 0 or end < start:
            raise ValueError("invalid_repair_plan")
        return BoltCodingPlan.model_validate(json.loads(text[start:end + 1]))

    def _record_device_events(self, command, output):
        for item in ((output.get("evidence") or {}).get("events") or [])[:200]:
            if isinstance(item, dict) and re.fullmatch(r"[a-z_]+(?:\.[a-z_]+)+", str(item.get("type") or "")):
                self._event(command, item["type"], {key: value for key, value in item.items() if key in {"status", "duration", "attempt", "changed_file_count", "path"}})

    def _event(self, command, action, metadata):
        AuditService(self.db).record(user_id=command.user_id, action=action, resource_type="bolt_project", resource_id=command.task_id, metadata={"task_id": command.task_id, "device_id": command.device_id, "agent_id": "bolt", **metadata})
