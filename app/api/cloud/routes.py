from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.core.database.session import get_db
from app.core.security.dependencies import get_current_user
from app.models.user import User
from app.schemas.cloud_runtime import CloudJobAccepted, CloudJobCreate, CloudJobRead, CloudJobResume
from app.services.cloud_runtime import CloudExecutionService, CloudJobError
from app.services.storage_service import StorageService


router = APIRouter(prefix="/cloud/jobs", tags=["cloud-jobs"])


def read_job(job) -> CloudJobRead:
    return CloudJobRead(
        id=job.id, task_id=job.task_id, request_id=job.request_id, agent_id=job.agent_id,
        capability=job.capability, status=job.status, execution_target=job.execution_target,
        workspace_id=job.workspace_id, current_step=job.current_step, progress=job.progress,
        attempt_count=job.attempt_count, max_attempts=job.max_attempts, result_summary=job.result_summary,
        failure_category=job.failure_category, safe_error=job.safe_error, pending_action=job.pending_action_json,
        created_at=job.created_at, started_at=job.started_at, updated_at=job.updated_at,
        completed_at=job.completed_at, cancelled_at=job.cancelled_at,
    )


@router.post("", response_model=CloudJobAccepted, status_code=status.HTTP_202_ACCEPTED)
def create_job(payload: CloudJobCreate, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    try:
        job = CloudExecutionService(db).create(user, payload)
    except CloudJobError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return CloudJobAccepted(job_id=job.id, task_id=job.task_id, workspace_id=job.workspace_id, status=job.status, created_at=job.created_at)


@router.get("", response_model=list[CloudJobRead])
def list_jobs(user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)], job_status: str | None = Query(default=None, alias="status")):
    return [read_job(job) for job in CloudExecutionService(db).list(user, status=job_status)]


@router.get("/{job_id}", response_model=CloudJobRead)
def get_job(job_id: str, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    job = CloudExecutionService(db).owned(user, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Cloud job not found")
    return read_job(job)


@router.get("/{job_id}/events")
def get_events(job_id: str, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    service = CloudExecutionService(db)
    if not service.owned(user, job_id):
        raise HTTPException(status_code=404, detail="Cloud job not found")
    return [{"id": item.id, "type": item.event_type, "sequence": item.sequence, "timestamp": item.timestamp, "payload": item.payload_json} for item in service.events(user, job_id)]


@router.post("/{job_id}/cancel", response_model=CloudJobRead)
def cancel_job(job_id: str, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    job = CloudExecutionService(db).cancel(user, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Cloud job not found")
    return read_job(job)


@router.post("/{job_id}/resume", response_model=CloudJobRead)
def resume_job(job_id: str, payload: CloudJobResume, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    job = CloudExecutionService(db).resume(user, job_id, payload.approved, payload.response)
    if not job:
        raise HTTPException(status_code=404, detail="Cloud job is not waiting for user input")
    return read_job(job)


@router.get("/{job_id}/artifacts")
def get_artifacts(job_id: str, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    service = CloudExecutionService(db)
    if not service.owned(user, job_id):
        raise HTTPException(status_code=404, detail="Cloud job not found")
    return [{"id": item.id, "type": item.artifact_type, "name": item.name, "content_type": item.content_type, "size": item.size_bytes, "checksum": item.checksum, "created_at": item.created_at} for item in service.artifacts(user, job_id)]


@router.get("/{job_id}/artifacts/{artifact_id}/download")
def download_artifact(job_id: str, artifact_id: str, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    artifact = next((item for item in CloudExecutionService(db).artifacts(user, job_id) if item.id == artifact_id), None)
    if not artifact:
        raise HTTPException(status_code=404, detail="Cloud artifact not found")
    try:
        content = StorageService().read_bytes(artifact.storage_key)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=404, detail="Cloud artifact content is unavailable") from exc
    return Response(content=content, media_type=artifact.content_type or "application/octet-stream", headers={"Content-Disposition": f'attachment; filename="{artifact.name}"'})


@router.get("/{job_id}/checkpoints")
def get_checkpoints(job_id: str, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    service = CloudExecutionService(db)
    if not service.owned(user, job_id):
        raise HTTPException(status_code=404, detail="Cloud job not found")
    return [{"id": item.id, "step": item.step_index, "state": item.state_json, "revision": item.revision_reference, "created_at": item.created_at} for item in service.checkpoints(user, job_id)]
