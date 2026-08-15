from __future__ import annotations

from datetime import timedelta

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.cloud_runtime import CloudJob
from app.models.mixins import utc_now


ACTIVE = ("QUEUED", "RETRYING")
TERMINAL = ("COMPLETED", "FAILED", "CANCELLED")


class DurableCloudQueue:
    """Database queue. PostgreSQL uses row locking with SKIP LOCKED."""

    def __init__(self, db: Session, *, lease_seconds: int = 90):
        self.db = db
        self.lease_seconds = lease_seconds

    def enqueue(self, job: CloudJob) -> CloudJob:
        now = utc_now()
        job.status = "QUEUED"
        job.available_at = now
        job.updated_at = now
        self.db.flush()
        return job

    def claim_next(self, worker_id: str) -> CloudJob | None:
        now = utc_now()
        query = self.db.query(CloudJob).filter(
            CloudJob.status.in_(ACTIVE),
            or_(CloudJob.available_at.is_(None), CloudJob.available_at <= now),
            or_(CloudJob.lease_expires_at.is_(None), CloudJob.lease_expires_at < now),
        ).order_by(CloudJob.created_at.asc())
        if self.db.bind and self.db.bind.dialect.name == "postgresql":
            query = query.with_for_update(skip_locked=True)
        job = query.first()
        if not job:
            return None
        job.status = "RUNNING"
        job.claimed_by = worker_id
        job.started_at = job.started_at or now
        job.heartbeat_at = now
        job.lease_expires_at = now + timedelta(seconds=self.lease_seconds)
        job.attempt_count += 1
        job.updated_at = now
        self.db.commit()
        self.db.refresh(job)
        return job

    def heartbeat(self, job: CloudJob, worker_id: str) -> bool:
        if job.claimed_by != worker_id or job.status != "RUNNING":
            return False
        now = utc_now()
        job.heartbeat_at = now
        job.lease_expires_at = now + timedelta(seconds=self.lease_seconds)
        job.updated_at = now
        self.db.commit()
        return True

    def acknowledge(self, job: CloudJob) -> None:
        now = utc_now()
        job.status = "COMPLETED"
        job.progress = 1
        job.completed_at = now
        job.updated_at = now
        job.lease_expires_at = None
        self.db.commit()

    def retry(self, job: CloudJob, *, category: str, safe_error: str, delay_seconds: int = 10) -> None:
        now = utc_now()
        if job.attempt_count >= job.max_attempts:
            job.status = "FAILED"
            job.completed_at = now
        else:
            job.status = "RETRYING"
            job.available_at = now + timedelta(seconds=delay_seconds)
        job.failure_category = category
        job.safe_error = safe_error
        job.claimed_by = None
        job.lease_expires_at = None
        job.updated_at = now
        self.db.commit()

    def cancel(self, job: CloudJob) -> None:
        now = utc_now()
        job.status = "CANCELLED"
        job.cancelled_at = now
        job.updated_at = now
        job.lease_expires_at = None
        self.db.commit()

    def release_stale(self) -> int:
        now = utc_now()
        stale = self.db.query(CloudJob).filter(CloudJob.status == "RUNNING", CloudJob.lease_expires_at < now).all()
        for job in stale:
            if job.attempt_count >= job.max_attempts:
                job.status, job.failure_category, job.safe_error = "FAILED", "worker_interruption", "Worker lease expired."
                job.completed_at = now
            else:
                job.status, job.available_at = "RETRYING", now
            job.claimed_by = None
            job.lease_expires_at = None
            job.updated_at = now
        self.db.commit()
        return len(stale)
