from fastapi.testclient import TestClient

from app.main import create_app

client = TestClient(create_app())


def test_waitlist_join_returns_success_for_valid_email(monkeypatch):
    def fake_send_test_email(email: str):
        return {"id": "email-123"}

    monkeypatch.setattr("app.api.waitlist.routes.send_test_email", fake_send_test_email)

    response = client.post(
        "/api/v1/waitlist",
        json={"email": "user@example.com"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "message": "Successfully joined the launch list.",
    }
