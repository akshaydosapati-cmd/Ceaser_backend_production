from datetime import timedelta
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database.base import Base
from app.models.audit_log import AuditLog
from app.models.desktop import DesktopCommand
from app.models.integration import Integration
from app.models.mixins import utc_now
from app.models.user import User
from app.services.bolt_repair_service import BoltRepairService
from app.services.github_project_service import GitHubProjectService


engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def reset():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


class GitHubStub:
    def __init__(self):
        self.tokens = []

    def create_repository(self, integration, **_):
        self.tokens.append(integration.access_token)
        return {"repository": {"full_name": "owner/project", "url": "https://github.com/owner/project"}, "visibility": "private", "verified": True}


def test_github_write_requires_confirmation_and_uses_only_requesting_users_integration(monkeypatch):
    reset()
    with Session() as db:
        first = User(email="first@example.com"); second = User(email="second@example.com")
        db.add_all([first, second]); db.flush()
        one = Integration(user_id=first.id, provider="github", status="connected"); one.access_token = "first-secret-token"
        two = Integration(user_id=second.id, provider="github", status="connected"); two.access_token = "second-secret-token"
        db.add_all([one, two]); db.commit()
        service = GitHubProjectService(db); provider = GitHubStub(); service.provider = provider
        monkeypatch.setattr(service, "_set_remote", lambda *args: None)
        monkeypatch.setattr(service, "_device", lambda *_args: {"status": "completed", "result": {"output": {"project": {"project_id": "p1", "display_name": "Project"}}}})
        assert service.execute(first, action="create", device_id="d1", project={"project_id": "p1", "display_name": "Project"}, confirmed=False)["error"] == "confirmation_required"
        result = service.execute(first, action="create", device_id="d1", project={"project_id": "p1", "display_name": "Project"}, confirmed=True)
        assert result["status"] == "completed" and provider.tokens == ["first-secret-token"]
        assert "first-secret-token" not in str(result)


def failed_command(db, attempt=0):
    user = User(email=f"repair-{attempt}@example.com"); db.add(user); db.flush()
    command = DesktopCommand(
        user_id=user.id, device_id="device-1", request_id=f"request-{attempt}", task_id="task-1", agent_id="bolt",
        capability="bolt.execute_plan", request_json={"metadata": {"repair_attempt": attempt}}, status="FAILED",
        result_json={"output": {"verified": False, "message": "build failed", "error_code": "build_failed", "project": {"project_id": "project-1", "display_name": "Project"}, "evidence": {"commands": [{"category": "build", "status": "failed"}], "files": ["src/app.js"]}}},
        expires_at=utc_now() + timedelta(minutes=5), updated_at=utc_now(),
    )
    db.add(command); db.commit(); db.refresh(command)
    return command


def test_failed_device_build_uses_model_router_and_queues_structured_bounded_repair(monkeypatch):
    reset()
    with Session() as db:
        command = failed_command(db)
        captured = {}
        def model(**kwargs):
            captured.update(kwargs)
            return '{"summary":"repair","file_operations":[{"operation":"write","path":"src/app.js","content":"fixed"}],"setup_commands":[],"build_commands":[{"argv":["npm","run","build"]}],"test_commands":[]}'
        monkeypatch.setattr("app.services.bolt_repair_service.generate_text_sync", model)
        monkeypatch.setattr("app.services.bolt_repair_service.DeviceGatewayService.submit", lambda _self, _user, request: SimpleNamespace(request_id=request.request_id))
        queued = BoltRepairService(db).handle(command)
        assert queued and ":repair:1:" in queued.request_id
        assert "first-secret-token" not in captured["input_text"] and ".env" not in captured["input_text"]
        actions = [row.action for row in db.query(AuditLog).order_by(AuditLog.created_at.asc()).all()]
        assert actions[-3:] == ["bolt.repair_started", "bolt.repair_plan_ready", "bolt.repair_applied"]


def test_repair_limit_is_honest_and_device_event_order_is_preserved(monkeypatch):
    reset()
    with Session() as db:
        monkeypatch.setattr("app.services.bolt_repair_service.settings.bolt_max_repair_attempts", 2)
        command = failed_command(db, attempt=2)
        output = command.result_json["output"]
        output["evidence"]["events"] = [
            {"type": "build.started", "status": "running"},
            {"type": "build.failed", "status": "failed"},
        ]
        assert BoltRepairService(db).handle(command) is None
        actions = [row.action for row in db.query(AuditLog).order_by(AuditLog.created_at.asc()).all()]
        assert actions == ["build.started", "build.failed", "bolt.failed"]


def test_github_safe_error_categories_do_not_echo_provider_secrets():
    secret = "ghp_never_return_this"
    result = GitHubProjectService._safe_call(lambda: (_ for _ in ()).throw(PermissionError(secret)))
    assert result == {"status": "failed", "error": "github_unauthorized"}
    assert secret not in str(result)
