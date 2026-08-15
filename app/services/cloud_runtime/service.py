from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config.settings import settings
from app.models.cloud_runtime import CloudArtifact, CloudCheckpoint, CloudJob, CloudJobEvent, CloudWorkspace
from app.models.mixins import utc_now
from app.models.user import User
from app.schemas.cloud_runtime import CloudJobCreate
from app.services.capabilities.registry import capability_registry

from .queue import DurableCloudQueue, TERMINAL


class CloudJobError(ValueError):
    pass


class CloudExecutionService:
    def __init__(self, db: Session):
        self.db = db
        self.queue = DurableCloudQueue(db, lease_seconds=settings.cloud_worker_lease_seconds)

    def create(self, user: User, payload: CloudJobCreate) -> CloudJob:
        capability = capability_registry.get(payload.capability)
        if not capability or not any(target.value == "CLOUD" for target in capability.allowed_execution_targets):
            raise CloudJobError("Capability is not available for cloud execution")
        active = self.db.query(CloudJob).filter(CloudJob.user_id == user.id, ~CloudJob.status.in_(TERMINAL)).count()
        if active >= settings.cloud_jobs_per_user:
            raise CloudJobError("Concurrent cloud job limit reached")
        if payload.idempotency_key:
            existing = self.db.query(CloudJob).filter(
                CloudJob.user_id == user.id, CloudJob.idempotency_key == payload.idempotency_key,
            ).first()
            if existing:
                return existing
        now = utc_now()
        job = CloudJob(
            user_id=user.id, agent_id=payload.agent_id, task_id=payload.task_id, request_id=payload.request_id,
            idempotency_key=payload.idempotency_key, capability=payload.capability, arguments_json=payload.arguments,
            max_attempts=settings.cloud_job_max_attempts, available_at=now, updated_at=now,
            parent_job_id=payload.parent_job_id, metadata_json=self._safe(payload.metadata),
            status="WAITING_FOR_USER" if payload.requires_confirmation else "QUEUED",
            pending_action_json={"type": "confirmation", "prompt": "Approve cloud execution?"} if payload.requires_confirmation else None,
        )
        self.db.add(job)
        try:
            self.db.flush()
        except IntegrityError:
            self.db.rollback()
            if payload.idempotency_key:
                return self.db.query(CloudJob).filter(CloudJob.user_id == user.id, CloudJob.idempotency_key == payload.idempotency_key).one()
            raise
        workspace = CloudWorkspace(
            user_id=user.id, job_id=job.id, project_id=payload.project_id, status="ACTIVE", source_type="generated",
            storage_location=f"supabase://{settings.supabase_storage_bucket}/cloud/{user.id}/{job.id}/",
            updated_at=now, limits_json={"max_bytes": settings.cloud_workspace_max_bytes},
        )
        self.db.add(workspace)
        self.db.flush()
        job.workspace_id = workspace.id
        if not payload.requires_confirmation:
            self.queue.enqueue(job)
        self.event(job, "cloud.job.created", {"capability": job.capability})
        self.event(job, "cloud.job.queued" if job.status == "QUEUED" else "cloud.job.waiting_for_user", {})
        self.db.commit()
        self.db.refresh(job)
        return job

    def owned(self, user: User, job_id: str) -> CloudJob | None:
        return self.db.query(CloudJob).filter(CloudJob.id == job_id, CloudJob.user_id == user.id).first()

    def list(self, user: User, *, status: str | None = None) -> list[CloudJob]:
        query = self.db.query(CloudJob).filter(CloudJob.user_id == user.id)
        if status:
            query = query.filter(CloudJob.status == status.upper())
        return query.order_by(CloudJob.created_at.desc()).limit(100).all()

    def events(self, user: User, job_id: str) -> list[CloudJobEvent]:
        return self.db.query(CloudJobEvent).filter(CloudJobEvent.user_id == user.id, CloudJobEvent.job_id == job_id).order_by(CloudJobEvent.sequence).all()

    def artifacts(self, user: User, job_id: str) -> list[CloudArtifact]:
        return self.db.query(CloudArtifact).filter(CloudArtifact.user_id == user.id, CloudArtifact.job_id == job_id).order_by(CloudArtifact.created_at).all()

    def checkpoints(self, user: User, job_id: str) -> list[CloudCheckpoint]:
        return self.db.query(CloudCheckpoint).filter(CloudCheckpoint.user_id == user.id, CloudCheckpoint.job_id == job_id).order_by(CloudCheckpoint.step_index).all()

    def cancel(self, user: User, job_id: str) -> CloudJob | None:
        job = self.owned(user, job_id)
        if not job or job.status in TERMINAL:
            return job
        self.queue.cancel(job)
        self.event(job, "cloud.job.cancelled", {})
        self.db.commit()
        return job

    def resume(self, user: User, job_id: str, approved: bool, response: str | None = None) -> CloudJob | None:
        job = self.owned(user, job_id)
        if not job or job.status != "WAITING_FOR_USER":
            return job
        if not approved:
            return self.cancel(user, job_id)
        job.pending_action_json = None
        job.metadata_json = {**(job.metadata_json or {}), "confirmation_response": response or "approved"}
        self.queue.enqueue(job)
        self.event(job, "cloud.job.queued", {"resumed": True})
        self.db.commit()
        return job

    def checkpoint(self, job: CloudJob, step: int, state: dict) -> CloudCheckpoint:
        item = CloudCheckpoint(user_id=job.user_id, job_id=job.id, workspace_id=job.workspace_id, step_index=step, state_json=self._safe(state))
        self.db.add(item)
        self.event(job, "cloud.job.checkpoint", {"step": step})
        self.db.commit()
        return item

    def event(self, job: CloudJob, event_type: str, payload: dict) -> CloudJobEvent:
        sequence = int(self.db.query(func.coalesce(func.max(CloudJobEvent.sequence), 0)).filter(CloudJobEvent.job_id == job.id).scalar()) + 1
        event = CloudJobEvent(job_id=job.id, user_id=job.user_id, event_type=event_type, sequence=sequence, timestamp=utc_now(), payload_json=self._safe(payload))
        self.db.add(event)
        self.db.flush()
        return event

    @staticmethod
    def _safe(payload: dict) -> dict:
        blocked = {"token", "access_token", "refresh_token", "authorization", "api_key", "secret", "password"}
        return {key: value for key, value in payload.items() if key.lower() not in blocked}
