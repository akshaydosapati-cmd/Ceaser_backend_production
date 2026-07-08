import os
from collections.abc import Generator

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["GEMINI_API_KEY"] = ""
os.environ["GOOGLE_CLIENT_ID"] = ""
os.environ["GOOGLE_CLIENT_SECRET"] = ""
os.environ["NOTION_CLIENT_ID"] = ""
os.environ["NOTION_CLIENT_SECRET"] = ""

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database.base import Base
from app.core.database.session import get_db
from app.core.security.dependencies import get_current_user
from app.main import create_app
from app.models.integration import Integration
from app.models.user import User


engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def override_db() -> Generator[Session, None, None]:
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


def override_current_user() -> User:
    db = TestingSessionLocal()
    user = db.query(User).filter(User.email == "integration@example.com").first()
    if not user:
        user = User(email="integration@example.com")
        db.add(user)
        db.commit()
        db.refresh(user)
    db.close()
    return user


Base.metadata.create_all(bind=engine)
app = create_app()
app.dependency_overrides[get_db] = override_db
app.dependency_overrides[get_current_user] = override_current_user
client = TestClient(app)


def test_integration_provider_registry_and_dashboard_records() -> None:
    providers_response = client.get("/integrations/providers")
    assert providers_response.status_code == 200
    providers = providers_response.json()
    assert {provider["id"] for provider in providers} == {
        "google-calendar",
        "gmail",
        "google-drive",
        "google-tasks",
        "google-classroom",
        "notion",
    }
    assert all(provider["read_only"] for provider in providers)

    integrations_response = client.get("/integrations")
    assert integrations_response.status_code == 200
    integrations = integrations_response.json()
    assert len(integrations) == 6
    assert all(not item["connected"] for item in integrations)


def test_connect_without_oauth_credentials_marks_provider_actionable() -> None:
    response = client.post("/integrations/google-calendar/connect", json={})
    assert response.status_code == 200
    payload = response.json()
    assert payload["requires_credentials"] is True
    assert payload["integration"]["status"] == "credentials_required"

    status_response = client.get("/integrations/google-calendar/status")
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "credentials_required"

    disconnect_response = client.post("/integrations/google-calendar/disconnect")
    assert disconnect_response.status_code == 200
    assert disconnect_response.json()["status"] == "not_connected"


def test_integration_tokens_are_encrypted_at_model_layer() -> None:
    integration = Integration(user_id=override_current_user().id, provider="gmail", status="connected", metadata_json={})
    integration.access_token = "access-secret"
    integration.refresh_token = "refresh-secret"

    assert integration.access_token_encrypted != "access-secret"
    assert integration.refresh_token_encrypted != "refresh-secret"
    assert integration.access_token == "access-secret"
    assert integration.refresh_token == "refresh-secret"


def test_metadata_endpoint_is_read_only_and_safe_when_disconnected() -> None:
    response = client.get("/integrations/notion/metadata")
    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "notion"
    assert payload["status"] == "not_connected"
    assert payload["items"] == []
