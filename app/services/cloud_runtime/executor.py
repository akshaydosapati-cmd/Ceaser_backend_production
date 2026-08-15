from __future__ import annotations

from app.execution.placement import ExecutionRequest
from app.models.user import User
from app.schemas.cloud_runtime import CloudJobCreate
from app.core.config.settings import settings

from .service import CloudExecutionService


class PersistentCloudExecutor:
    """Consumes a Stage 23 CLOUD request and persists it without blocking."""

    available = True

    def __init__(self, service: CloudExecutionService, user: User):
        self.service = service
        self.user = user

    def submit(self, request: ExecutionRequest) -> dict:
        if request.user_id != self.user.id:
            raise PermissionError("Execution request owner mismatch")
        if self._is_software_engineering(request) and not settings.cloud_coding_enabled:
            raise RuntimeError("cloud_coding_disabled")
        job = self.service.create(self.user, CloudJobCreate(
            agent_id=request.agent_id, task_id=request.task_id, request_id=request.request_id,
            capability=request.capability, arguments=request.arguments,
            project_id=request.project_context.project_id if request.project_context else None,
            idempotency_key=str(request.metadata.get("idempotency_key") or request.request_id),
            requires_confirmation=request.requires_confirmation and not request.confirmed,
            metadata=request.metadata,
        ))
        return {"job_id": job.id, "task_id": job.task_id, "workspace_id": job.workspace_id, "status": job.status, "created_at": job.created_at}

    @staticmethod
    def _is_software_engineering(request: ExecutionRequest) -> bool:
        workload = str(request.metadata.get("workload") or "").lower()
        return workload == "software_engineering" or (
            request.agent_id.lower() == "bolt"
            and request.capability.split(".", 1)[0] in {"project", "filesystem", "terminal", "git", "build", "test", "development"}
        )
