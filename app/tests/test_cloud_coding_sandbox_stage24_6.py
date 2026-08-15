import base64
import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config.settings import settings
from app.core.database.base import Base
from app.models.cloud_runtime import CloudArtifact, CloudJob
from app.models.user import User
from app.schemas.cloud_runtime import CloudJobCreate
from app.services.cloud_runtime import CloudExecutionService, DurableCloudQueue
from app.services.sandbox import SandboxCommand, SandboxCommandResult, SandboxHandle, SandboxLimits, SandboxProvider
from app.services.sandbox.bolt_runner import BoltCloudCodingRunner
from app.services.sandbox.docker import DockerSandboxProvider
from app.services.sandbox.paths import confined_path
from app.services.sandbox.workspace import DurableSandboxWorkspace
from app.services.storage_service import StorageService


engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
BLOBS = {}


class FakeSandbox(SandboxProvider):
    name = "fake-isolated"
    available = True

    def __init__(self, fail_build=False):
        self.environments = {}
        self.destroyed = []
        self.fail_build = fail_build
        self.restores = 0
        self.counter = 0

    def create(self, *, owner_id, job_id, limits):
        self.counter += 1
        sandbox_id = f"sandbox-{self.counter}"
        self.environments[sandbox_id] = {"owner": owner_id, "job": job_id, "files": {}}
        return SandboxHandle(sandbox_id=sandbox_id, provider=self.name)

    def destroy(self, handle): self.destroyed.append(handle.sandbox_id)

    def execute(self, handle, command, *, cancel_check=None):
        if cancel_check and cancel_check():
            return SandboxCommandResult(status="cancelled")
        if command.argv[0] == "build" and self.fail_build:
            return SandboxCommandResult(status="failed", exit_code=1, stderr="compile failed")
        stdout = "abc123" if command.argv[:2] == ["git", "rev-parse"] else "ok"
        return SandboxCommandResult(status="completed", exit_code=0, stdout=stdout)

    def write_file(self, handle, path, content): self.environments[handle.sandbox_id]["files"][confined_path(path)] = content
    def read_file(self, handle, path): return self.environments[handle.sandbox_id]["files"][confined_path(path)]
    def list_files(self, handle): return sorted(self.environments[handle.sandbox_id]["files"])
    def list_directory(self, handle, path="."):
        prefix = "" if path == "." else confined_path(path).rstrip("/") + "/"
        return sorted({name[len(prefix):].split("/", 1)[0] for name in self.list_files(handle) if name.startswith(prefix)})
    def stat(self, handle, path):
        value = self.environments[handle.sandbox_id]["files"].get(confined_path(path))
        return {"exists": value is not None, "is_file": value is not None, "is_dir": False, "size": len(value or b"")}

    def file_operation(self, handle, operation, path, destination=None):
        files, path = self.environments[handle.sandbox_id]["files"], confined_path(path)
        if operation == "mkdir": return
        if operation == "delete": files.pop(path, None); return
        destination = confined_path(destination)
        files[destination] = files[path]
        if operation == "rename": files.pop(path)

    def export_archive(self, handle):
        files = self.environments[handle.sandbox_id]["files"]
        return json.dumps({key: base64.b64encode(value).decode() for key, value in files.items()}, sort_keys=True).encode()

    def restore_archive(self, handle, archive):
        self.restores += 1
        values = json.loads(archive)
        self.environments[handle.sandbox_id]["files"] = {key: base64.b64decode(value) for key, value in values.items()}

    def toolchains(self, _handle): return {"node": "v22", "npm": "10", "python": "3.12", "git": "2.45"}


@pytest.fixture(autouse=True)
def database(monkeypatch):
    Base.metadata.drop_all(engine); Base.metadata.create_all(engine); BLOBS.clear()
    monkeypatch.setattr(settings, "sandbox_max_build_retries", 0)
    monkeypatch.setattr(StorageService, "store", lambda _self, **kwargs: _store(kwargs["user_id"], kwargs["filename"], kwargs["content"]))
    monkeypatch.setattr(StorageService, "read_bytes", lambda _self, key: BLOBS[key])


def _store(user_id, filename, content):
    key = f"memory://{user_id}/{filename}"
    BLOBS[key] = content
    return key


def user(db, email="user@example.com"):
    item = User(email=email); db.add(item); db.commit(); db.refresh(item); return item


def coding_plan(name="index.html", content="<h1>Clinic</h1>", build="build"):
    return {
        "summary": "Build project",
        "file_operations": [{"operation": "write", "path": name, "content": content}],
        "build_commands": [{"argv": [build]}],
        "test_commands": [{"argv": ["test"]}],
    }


def job(db, owner, **arguments):
    created = CloudExecutionService(db).create(owner, CloudJobCreate(
        agent_id="bolt", task_id=f"task-{len(arguments)}", request_id=f"request-{len(arguments)}-{id(arguments)}",
        capability="project.build", arguments=arguments,
    ))
    return DurableCloudQueue(db).claim_next("sandbox-worker")


def test_workspace_paths_reject_traversal_and_absolute_paths():
    for path in ("../secret", "/etc/passwd", "folder/../../secret", "C:\\backend\\.env"):
        with pytest.raises(ValueError): confined_path(path)
    assert confined_path("src/app.tsx") == "src/app.tsx"


def test_fake_provider_isolates_generated_users_and_files():
    provider = FakeSandbox(); limits = SandboxLimits()
    one = provider.create(owner_id="user-a", job_id="a", limits=limits)
    two = provider.create(owner_id="user-b", job_id="b", limits=limits)
    provider.write_file(one, "secret.txt", b"A")
    assert provider.list_files(two) == [] and provider.read_file(one, "secret.txt") == b"A"


def test_command_cancellation_and_nonzero_are_structured():
    provider = FakeSandbox(fail_build=True)
    handle = provider.create(owner_id="u", job_id="j", limits=SandboxLimits())
    assert provider.execute(handle, SandboxCommand(argv=["build"])).status == "failed"
    assert provider.execute(handle, SandboxCommand(argv=["test"]), cancel_check=lambda: True).status == "cancelled"


def test_file_stat_and_workspace_copy_remain_scoped():
    provider = FakeSandbox(); handle = provider.create(owner_id="u", job_id="j", limits=SandboxLimits())
    provider.write_file(handle, "src/app.js", b"code")
    provider.file_operation(handle, "copy", "src/app.js", "src/app-copy.js")
    assert provider.stat(handle, "src/app-copy.js") == {"exists": True, "is_file": True, "is_dir": False, "size": 4}


def test_bolt_build_persists_verified_workspace_checkpoints_and_artifacts():
    provider = FakeSandbox()
    with Session() as db:
        owner = user(db); item = job(db, owner, coding_plan=coding_plan())
        BoltCloudCodingRunner(provider).run(item, CloudExecutionService(db), DurableCloudQueue(db))
        db.refresh(item)
        artifacts = db.query(CloudArtifact).filter_by(user_id=owner.id, job_id=item.id).all()
        assert item.status == "COMPLETED" and item.current_step == "verified"
        assert {artifact.artifact_type for artifact in artifacts} == {"workspace_snapshot", "manifest", "verification_log"}
        manifest = [artifact for artifact in artifacts if artifact.artifact_type == "manifest"][-1]
        assert json.loads(BLOBS[manifest.storage_key])["build_verified"] is True
        assert provider.destroyed


def test_existing_project_continuation_restores_then_modifies_minimum_files():
    provider = FakeSandbox()
    with Session() as db:
        owner = user(db)
        first = job(db, owner, coding_plan=coding_plan()); BoltCloudCodingRunner(provider).run(first, CloudExecutionService(db), DurableCloudQueue(db))
        second = job(db, owner, source_workspace_id=first.workspace_id, coding_plan=coding_plan("styles.css", "body{}"))
        BoltCloudCodingRunner(provider).run(second, CloudExecutionService(db), DurableCloudQueue(db))
        snapshot = db.query(CloudArtifact).filter_by(job_id=second.id, artifact_type="workspace_snapshot").order_by(CloudArtifact.created_at.desc()).first()
        files = json.loads(BLOBS[snapshot.storage_key])
        assert set(files) == {"index.html", "styles.css"} and provider.restores == 1


def test_cross_user_cannot_restore_another_users_workspace():
    provider = FakeSandbox()
    with Session() as db:
        one, two = user(db, "one@example.com"), user(db, "two@example.com")
        first = job(db, one, coding_plan=coding_plan()); BoltCloudCodingRunner(provider).run(first, CloudExecutionService(db), DurableCloudQueue(db))
        second = job(db, two, source_workspace_id=first.workspace_id, coding_plan=coding_plan("own.txt", "safe"))
        BoltCloudCodingRunner(provider).run(second, CloudExecutionService(db), DurableCloudQueue(db))
        snapshot = db.query(CloudArtifact).filter_by(job_id=second.id, artifact_type="workspace_snapshot").order_by(CloudArtifact.created_at.desc()).first()
        assert set(json.loads(BLOBS[snapshot.storage_key])) == {"own.txt"}


def test_build_failure_never_reports_completed(monkeypatch):
    provider = FakeSandbox(fail_build=True)
    with Session() as db:
        owner = user(db); item = job(db, owner, coding_plan=coding_plan())
        with pytest.raises(ValueError, match="build_verification_failed"):
            BoltCloudCodingRunner(provider).run(item, CloudExecutionService(db), DurableCloudQueue(db))
        db.refresh(item)
        assert item.status != "COMPLETED"


def test_bounded_repair_can_turn_failed_build_into_verified_result(monkeypatch):
    provider = FakeSandbox(fail_build=True)
    repair = coding_plan("fixed.js", "fixed")
    with Session() as db:
        owner = user(db); item = job(db, owner, coding_plan=coding_plan(), repair_plans=[repair])
        original = provider.execute
        calls = {"build": 0}
        def execute(handle, command, **kwargs):
            if command.argv[0] == "build":
                calls["build"] += 1
                if calls["build"] > 1: provider.fail_build = False
            return original(handle, command, **kwargs)
        provider.execute = execute
        monkeypatch.setattr(settings, "sandbox_max_build_retries", 1)
        BoltCloudCodingRunner(provider).run(item, CloudExecutionService(db), DurableCloudQueue(db))
        assert item.status == "COMPLETED" and calls["build"] == 2


def test_unsupplied_plan_uses_stage22_model_router(monkeypatch):
    calls = []
    monkeypatch.setattr("app.services.sandbox.bolt_runner.request_for_agent", lambda agent, **kwargs: calls.append((agent, kwargs)) or object())
    monkeypatch.setattr("app.services.sandbox.bolt_runner.generate_text_sync", lambda **_kwargs: json.dumps(coding_plan()))
    provider = FakeSandbox()
    with Session() as db:
        owner = user(db); item = job(db, owner, prompt="Build a dental clinic website")
        BoltCloudCodingRunner(provider).run(item, CloudExecutionService(db), DurableCloudQueue(db))
        assert calls[0][0] == "bolt" and item.status == "COMPLETED"


def test_sandbox_events_contain_no_owner_secrets():
    provider = FakeSandbox()
    with Session() as db:
        owner = user(db); item = job(db, owner, coding_plan=coding_plan(), api_key="must-not-propagate")
        BoltCloudCodingRunner(provider).run(item, CloudExecutionService(db), DurableCloudQueue(db))
        events = CloudExecutionService(db).events(owner, item.id)
        serialized = json.dumps([event.payload_json for event in events])
        assert "must-not-propagate" not in serialized


def test_workspace_restore_rejects_checksum_mismatch():
    provider = FakeSandbox()
    with Session() as db:
        owner = user(db); first = job(db, owner, coding_plan=coding_plan())
        BoltCloudCodingRunner(provider).run(first, CloudExecutionService(db), DurableCloudQueue(db))
        artifact = db.query(CloudArtifact).filter_by(job_id=first.id, artifact_type="workspace_snapshot").order_by(CloudArtifact.created_at.desc()).first()
        BLOBS[artifact.storage_key] = b"tampered"
        second = job(db, owner, source_workspace_id=first.workspace_id, coding_plan=coding_plan())
        handle = provider.create(owner_id=owner.id, job_id=second.id, limits=SandboxLimits())
        with pytest.raises(ValueError, match="workspace_checksum_mismatch"):
            DurableSandboxWorkspace(db).restore(second, provider, handle)


def test_docker_provider_creation_has_no_host_mounts_or_secret_environment(monkeypatch):
    calls = []
    class Result:
        returncode = 0
        stdout = "27.0"
        stderr = ""
    monkeypatch.setattr("app.services.sandbox.docker.subprocess.run", lambda argv, **_kwargs: calls.append(argv) or Result())
    provider = DockerSandboxProvider(image="sandbox:test", network_mode="none")
    provider.create(owner_id="generated-user", job_id="generated-job", limits=SandboxLimits())
    create = calls[1]
    assert "--read-only" in create and ["--cap-drop", "ALL"] == create[create.index("--cap-drop"):create.index("--cap-drop") + 2]
    assert "--privileged" not in create and "-v" not in create and "--env" not in create and "--network" in create
