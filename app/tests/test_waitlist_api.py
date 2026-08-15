from collections.abc import Generator

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database.session import get_db
from app.main import create_app

engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
with engine.begin() as connection:
    connection.execute(text("""
        CREATE TABLE launch_waitlist (
            id TEXT PRIMARY KEY, email TEXT NOT NULL UNIQUE, name TEXT, source TEXT,
            status TEXT, created_at DATETIME, updated_at DATETIME
        )
    """))


def override_db() -> Generator[Session, None, None]:
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app = create_app()
app.dependency_overrides[get_db] = override_db
client = TestClient(app)


def test_waitlist_join_returns_success_for_valid_email(monkeypatch):
    def fake_send_test_email(email: str):
        return {"id": "email-123"}

    monkeypatch.setattr("app.api.waitlist.routes.send_test_email", fake_send_test_email)

    with engine.begin() as connection:
        connection.execute(text("DELETE FROM launch_waitlist"))

    response = client.post(
        "/api/v1/waitlist",
        json={"email": "user@example.com"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "message": "Successfully joined the launch list.",
    }
