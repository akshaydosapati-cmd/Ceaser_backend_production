from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.core.database.base import Base
from app.models.user import User
from app.services.capabilities.registry import CapabilityRegistry
from app.services.capabilities.schemas import CapabilityManifest
from app.services.usage_ledger_service import UsageLedgerService


engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
Session = sessionmaker(bind=engine)


def test_c5_manifests_aliases_unknown_plugins_and_usage_identity():
    registry = CapabilityRegistry()
    expected = {
        "applications.open": ("local", "free", "low", True),
        "files.delete": ("local", "free", "high", True),
        "github.list_issues": ("plugin", "negligible", "low", True),
        "github.analyze_repository": ("hybrid", "variable", "low", False),
        "notion.read_page": ("plugin", "negligible", "low", True),
        "voice.simple_command": ("local", "free", "low", True),
        "voice.ai_conversation": ("hybrid", "variable", "low", False),
        "document.create_file": ("artifact", "negligible", "low", True),
        "document.generate_content": ("ai", "variable", "low", False),
        "workforce.run_job": ("workforce", "high", "medium", False),
    }
    for key, values in expected.items():
        manifest = registry.resolve_manifest(key)
        assert (manifest.execution_type, manifest.cost_class, manifest.risk_level, manifest.lite_allowed) == values
        assert manifest.manifest_version == 1
    assert registry.resolve_manifest("open_app").key == "applications.open"
    unknown = registry.resolve_manifest("future.action")
    assert unknown.execution_type == "unknown" and unknown.cost_class == "unknown" and not unknown.lite_allowed

    class Plugin:
        @staticmethod
        def capability_manifests():
            return [CapabilityManifest("spotify.pause", "Pause Spotify", "media", "Pause playback.", "plugin", "negligible", "low", requires_plugin=True, requires_network=True, lite_allowed=True)]

    registry.register_plugin_manifests(Plugin())
    assert registry.resolve_manifest("spotify.pause").requires_plugin

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    db = Session()
    user = User(email="manifests-c5@ceaser.local")
    db.add(user)
    db.commit()
    event = UsageLedgerService(db).start(user_id=user.id, request_id="open", feature="native", operation="open_app")
    assert (event.capability_key, event.capability_category, event.execution_type) == ("applications.open", "applications", "local")
    missing = UsageLedgerService(db).start(user_id=user.id, request_id="future", feature="automation", operation="future.action")
    assert (missing.capability_key, missing.execution_type) == ("future.action", "unknown")
    db.close()
