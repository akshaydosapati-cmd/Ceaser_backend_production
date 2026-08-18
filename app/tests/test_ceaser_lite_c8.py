from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.core.database.base import Base
from app.models.commercial import ResourcePolicyDecision
from app.models.user import User
from app.services.lite_behavior import LiteExecutionResolver
from app.services.resource_policy_engine import PolicyDecision


engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
Session = sessionmaker(bind=engine)


def decision(key, value="ALLOW_LITE", confirmation=False):
    return PolicyDecision(value, "test", key, Decimal("1"), Decimal("0"), "LITE", "LITE", confirmation, "development-v1", False, "EXISTING_BEHAVIOR", {})


def test_c8_selective_lite_behaviors_and_observe_mode():
    Base.metadata.drop_all(engine); Base.metadata.create_all(engine)
    db = Session(); user = User(email="lite-c8@ceaser.local"); db.add(user); db.commit()
    resolver = LiteExecutionResolver(db)
    full = ["applications.open", "voice.simple_command", "github.list_issues", "notion.read_page", "document.create_file"]
    for key in full:
        result = resolver.resolve(policy_decision=decision(key), capability_key=key, rollout_mode="selective_enforce")
        assert result.should_execute and result.effective_capability == key and not result.upgrade_prompted
    deletion = resolver.resolve(policy_decision=decision("files.delete", confirmation=True), capability_key="files.delete", rollout_mode="selective_enforce")
    assert deletion.should_execute and deletion.requires_confirmation

    supplied = resolver.resolve(policy_decision=decision("document.generate_content", "ALLOW_DEGRADED"), capability_key="document.generate_content", rollout_mode="selective_enforce", request_context={"content_supplied": True})
    assert supplied.should_execute and supplied.fallback_capability == "document.create_file"
    generated = resolver.resolve(policy_decision=decision("document.generate_content", "ALLOW_DEGRADED"), capability_key="document.generate_content", rollout_mode="selective_enforce")
    voice = resolver.resolve(policy_decision=decision("voice.ai_conversation", "ALLOW_DEGRADED"), capability_key="voice.ai_conversation", rollout_mode="selective_enforce")
    workforce = resolver.resolve(policy_decision=decision("workforce.run_job", "REQUIRE_UPGRADE"), capability_key="workforce.run_job", rollout_mode="selective_enforce")
    assert not generated.should_execute and generated.upgrade_prompted and generated.response_key == "lite.ai_generation_limited"
    assert not voice.should_execute and voice.upgrade_prompted and voice.response_key == "lite.compute_exhausted"
    assert not workforce.should_execute and workforce.response_key == "lite.workforce_upgrade_required"

    unknown = resolver.resolve(policy_decision=decision("future.action", "UNKNOWN"), capability_key="future.action", rollout_mode="selective_enforce")
    observed = resolver.resolve(policy_decision=decision("workforce.run_job", "REQUIRE_UPGRADE"), capability_key="workforce.run_job", rollout_mode="observe")
    assert unknown.should_execute and unknown.effective_execution_mode == "EXISTING_BEHAVIOR"
    assert observed.should_execute and observed.effective_execution_mode == "EXISTING_BEHAVIOR"

    audit = ResourcePolicyDecision(user_id=user.id, request_id="audit", capability_key="workforce.run_job", decision="REQUIRE_UPGRADE", reason="test", policy_version="development-v1", execution_mode="BLOCKED", enforced=False)
    db.add(audit); db.flush()
    with_record = PolicyDecision("REQUIRE_UPGRADE", "test", "workforce.run_job", Decimal("250"), Decimal("0"), "BLOCKED", None, False, "development-v1", False, "EXISTING_BEHAVIOR", {}, audit.id)
    resolver.resolve(policy_decision=with_record, capability_key="workforce.run_job", rollout_mode="selective_enforce")
    db.refresh(audit)
    assert audit.effective_execution_mode == "UPGRADE_REQUIRED" and audit.upgrade_prompted and audit.lite_behavior_version == "c8-v1"
    db.close()
