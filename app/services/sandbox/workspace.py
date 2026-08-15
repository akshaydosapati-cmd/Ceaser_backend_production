from __future__ import annotations

import hashlib
import json
from uuid import uuid4

from sqlalchemy.orm import Session

from app.core.config.settings import settings
from app.models.cloud_runtime import CloudArtifact, CloudJob, CloudWorkspace
from app.services.storage_service import StorageService

from .base import SandboxProvider
from .models import SandboxHandle, SandboxManifest


class DurableSandboxWorkspace:
    def __init__(self, db: Session, storage: StorageService | None = None):
        self.db = db
        self.storage = storage or StorageService()

    def restore(self, job: CloudJob, provider: SandboxProvider, handle: SandboxHandle) -> CloudArtifact | None:
        artifact = self._latest_snapshot(job)
        if not artifact:
            return None
        content = self.storage.read_bytes(artifact.storage_key)
        if artifact.checksum and hashlib.sha256(content).hexdigest() != artifact.checksum:
            raise ValueError("workspace_checksum_mismatch")
        provider.restore_archive(handle, content)
        return artifact

    def persist(self, job: CloudJob, provider: SandboxProvider, handle: SandboxHandle, manifest: SandboxManifest) -> list[CloudArtifact]:
        archive = provider.export_archive(handle)
        snapshot = self._artifact(job, "workspace_snapshot", "workspace.tar.gz", archive, "application/gzip", {"revision": manifest.revision})
        manifest_bytes = json.dumps(manifest.model_dump(mode="json"), sort_keys=True).encode("utf-8")
        metadata = self._artifact(job, "manifest", "manifest.json", manifest_bytes, "application/json", {})
        workspace = self.db.get(CloudWorkspace, job.workspace_id)
        if workspace:
            workspace.storage_location = snapshot.storage_key
            workspace.updated_at = job.updated_at
        self.db.flush()
        return [snapshot, metadata]

    def persist_log(self, job: CloudJob, name: str, content: bytes) -> CloudArtifact:
        return self._artifact(job, "verification_log", name, content, "text/plain", {})

    def _latest_snapshot(self, job: CloudJob) -> CloudArtifact | None:
        query = self.db.query(CloudArtifact).filter(
            CloudArtifact.user_id == job.user_id,
            CloudArtifact.artifact_type == "workspace_snapshot",
        )
        arguments = job.arguments_json or {}
        source_workspace_id = arguments.get("source_workspace_id") or arguments.get("workspace_id")
        if source_workspace_id:
            query = query.filter(CloudArtifact.workspace_id == str(source_workspace_id))
        elif job.workspace_id:
            own = query.filter(CloudArtifact.workspace_id == job.workspace_id).order_by(CloudArtifact.created_at.desc()).first()
            if own:
                return own
            workspace = self.db.get(CloudWorkspace, job.workspace_id)
            if workspace and workspace.project_id:
                workspace_ids = self.db.query(CloudWorkspace.id).filter(
                    CloudWorkspace.user_id == job.user_id,
                    CloudWorkspace.project_id == workspace.project_id,
                    CloudWorkspace.id != workspace.id,
                )
                query = query.filter(CloudArtifact.workspace_id.in_(workspace_ids))
            else:
                return None
        return query.order_by(CloudArtifact.created_at.desc()).first()

    def _artifact(self, job: CloudJob, artifact_type: str, name: str, content: bytes, content_type: str, metadata: dict) -> CloudArtifact:
        limit = settings.cloud_workspace_max_bytes if artifact_type == "workspace_snapshot" else settings.cloud_artifact_max_bytes
        if len(content) > limit:
            raise ValueError("artifact_too_large")
        filename = f"cloud-{job.id}-{artifact_type}-{uuid4().hex[:12]}-{name}"
        storage_key = self.storage.store(user_id=job.user_id, filename=filename, content=content, content_type=content_type)
        artifact = CloudArtifact(
            user_id=job.user_id, job_id=job.id, workspace_id=job.workspace_id, artifact_type=artifact_type,
            name=name, storage_key=storage_key, content_type=content_type, size_bytes=len(content),
            checksum=hashlib.sha256(content).hexdigest(), metadata_json=metadata,
        )
        self.db.add(artifact)
        self.db.flush()
        return artifact
