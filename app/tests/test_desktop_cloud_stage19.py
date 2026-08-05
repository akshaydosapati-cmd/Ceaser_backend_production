from __future__ import annotations

import os
import hashlib
import re
from collections.abc import Generator
from datetime import datetime, timedelta, timezone

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["JWT_SECRET"] = "stage19-test-secret"
os.environ["GEMINI_API_KEY"] = ""

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database.base import Base
from app.core.database.session import get_db
from app.core.security.dependencies import get_current_user
from app.api.auth.routes import router as auth_router
from app.api.desktop.routes import router as desktop_router
from app.models.desktop import DesktopAuthCode, DesktopCloudResource
from app.models.user import User


engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def override_db() -> Generator[Session, None, None]:
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


def user_for(email: str) -> User:
    db = TestingSessionLocal()
    user = db.query(User).filter(User.email == email).first()
    if not user:
        user = User(email=email)
        db.add(user)
        db.commit()
        db.refresh(user)
    db.close()
    return user


def override_current_user() -> User:
    return user_for("desktop@example.com")


Base.metadata.drop_all(bind=engine)
Base.metadata.create_all(bind=engine)
app = FastAPI()
app.include_router(auth_router)
app.include_router(desktop_router)
app.dependency_overrides[get_db] = override_db
app.dependency_overrides[get_current_user] = override_current_user
client = TestClient(app)


def authorize_payload(**patch):
    payload = {
        "state": "state-123456",
        "code_challenge": "j-fNzdlzZ7AtHak-EkSdlNjdhjhDjxw9h1CX6MoMrY4",
        "code_challenge_method": "S256",
        "redirect_uri": "ceaser://auth/callback",
        "device_id": "device-a",
        "device_name": "Akshay Laptop",
        "platform": "win32",
        "app_version": "0.1.1",
    }
    payload.update(patch)
    return payload


def exchange_payload(code: str, verifier: str = "stage19-verifier-01234567890123456789"):
    return {
        "code": code,
        "code_verifier": verifier,
        "redirect_uri": "ceaser://auth/callback",
        "device": {
            "device_id": "device-a",
            "device_name": "Akshay Laptop",
            "platform": "win32",
            "app_version": "0.1.1",
        },
    }


def create_desktop_session():
    response = client.post("/auth/desktop/authorize", json=authorize_payload())
    assert response.status_code == 200, response.text
    code = response.json()["code"]
    exchanged = client.post("/auth/desktop/exchange", json=exchange_payload(code))
    assert exchanged.status_code == 200, exchanged.text
    return exchanged.json()


def authorize_code(device_id: str = "device-a") -> str:
    response = client.post("/auth/desktop/authorize", json=authorize_payload(device_id=device_id))
    assert response.status_code == 200, response.text
    return response.json()["code"]


def test_successful_desktop_authorization_and_exchange():
    session = create_desktop_session()
    assert session["access_token"].startswith("cdat.")
    assert session["refresh_token"].startswith("dtr_")
    assert session["user"]["email"] == "desktop@example.com"


def test_invalid_state_shape_rejected():
    response = client.post("/auth/desktop/authorize", json=authorize_payload(state="short"))
    assert response.status_code == 422


def test_wrong_pkce_verifier_rejected():
    response = client.post("/auth/desktop/authorize", json=authorize_payload(device_id="device-pkce"))
    code = response.json()["code"]
    payload = exchange_payload(code, verifier="wrong-verifier-01234567890123456789")
    payload["device"]["device_id"] = "device-pkce"
    exchanged = client.post("/auth/desktop/exchange", json=payload)
    assert exchanged.status_code == 400


def test_expired_code_and_reused_code_are_rejected():
    code = authorize_code("device-reuse")
    payload = exchange_payload(code)
    payload["device"]["device_id"] = "device-reuse"
    first = client.post("/auth/desktop/exchange", json=payload)
    assert first.status_code == 200
    reused = client.post("/auth/desktop/exchange", json=payload)
    assert reused.status_code == 400

    expired_code = authorize_code("device-expired")
    db = TestingSessionLocal()
    record = db.query(DesktopAuthCode).filter(DesktopAuthCode.device_id == "device-expired").first()
    record.expires_at = datetime.now(timezone.utc) - timedelta(seconds=5)
    db.commit()
    db.close()
    expired_payload = exchange_payload(expired_code)
    expired_payload["device"]["device_id"] = "device-expired"
    expired = client.post("/auth/desktop/exchange", json=expired_payload)
    assert expired.status_code == 400


def test_refresh_and_revoked_device():
    session = create_desktop_session()
    refreshed = client.post("/auth/desktop/refresh", json={"refresh_token": session["refresh_token"], "device_id": "device-a"})
    assert refreshed.status_code == 200
    revoked = client.delete("/desktop/devices/device-a", headers={"Authorization": f"Bearer {session['access_token']}"})
    assert revoked.status_code == 200
    denied = client.post("/auth/desktop/refresh", json={"refresh_token": session["refresh_token"], "device_id": "device-a"})
    assert denied.status_code == 401


def test_connected_devices_list():
    session = create_desktop_session()
    response = client.get("/desktop/devices", headers={"Authorization": f"Bearer {session['access_token']}"})
    assert response.status_code == 200
    assert response.json()[0]["device_id"] == "device-a"


def test_cloud_resource_create_latest_search_read_update_delete_restore_download():
    session = create_desktop_session()
    headers = {"Authorization": f"Bearer {session['access_token']}"}
    created = client.post("/desktop/cloud/create", json={"name": "Launch Report", "resource_type": "report", "content": "Plan"}, headers=headers)
    assert created.status_code == 200
    resource_id = created.json()["resource"]["id"]

    latest = client.post("/desktop/cloud/latest", json={"resource_type": "report"}, headers=headers)
    assert latest.json()["resource"]["id"] == resource_id
    search = client.post("/desktop/cloud/search", json={"query": "Launch"}, headers=headers)
    assert search.json()["items"][0]["id"] == resource_id
    read = client.post("/desktop/cloud/read", json={"resource_id": resource_id}, headers=headers)
    assert read.json()["resource"]["name"] == "Launch Report"
    updated = client.post("/desktop/cloud/update", json={"resource_id": resource_id, "name": "Launch Report v2"}, headers=headers)
    assert updated.json()["resource"]["version"] == 2
    deleted = client.post("/desktop/cloud/delete", json={"resource_id": resource_id}, headers=headers)
    assert deleted.json()["resource"]["status"] == "deleted"
    restored = client.post("/desktop/cloud/restore", json={"resource_id": resource_id}, headers=headers)
    assert restored.json()["resource"]["status"] == "active"
    download = client.post("/desktop/cloud/download", json={"resource_id": resource_id}, headers=headers)
    assert download.status_code == 404


def test_cross_user_resource_isolation():
    user_a = user_for("desktop@example.com")
    user_b = user_for("other@example.com")
    db = TestingSessionLocal()
    db.add(DesktopCloudResource(user_id=user_b.id, name="Private Other Report", resource_type="report", version=1, status="active", metadata_json={}))
    db.commit()
    db.close()
    session = create_desktop_session()
    response = client.post("/desktop/cloud/search", json={"query": "Private Other"}, headers={"Authorization": f"Bearer {session['access_token']}"})
    assert response.status_code == 200
    assert response.json()["items"] == []
    assert user_a.id != user_b.id


def test_upload_validation_and_signed_upload_url():
    session = create_desktop_session()
    headers = {"Authorization": f"Bearer {session['access_token']}"}
    bad = client.post("/desktop/cloud/upload", json={"name": "bad.exe", "mime_type": "application/x-msdownload", "size_bytes": 100}, headers=headers)
    assert bad.status_code == 415
    good = client.post("/desktop/cloud/upload", json={"name": "notes.pdf", "mime_type": "application/pdf", "size_bytes": 2000}, headers=headers)
    assert good.status_code == 200
    assert good.json()["signed_upload_url"]


def test_real_signed_upload_and_download_bytes_round_trip():
    session = create_desktop_session()
    headers = {"Authorization": f"Bearer {session['access_token']}"}
    content = b"%PDF-1.4\nCEASER desktop cloud upload test\n%%EOF"
    expected_sha = hashlib.sha256(content).hexdigest()

    init = client.post(
        "/desktop/cloud/upload",
        json={"name": "stage19.pdf", "mime_type": "application/pdf", "size_bytes": len(content)},
        headers=headers,
    )
    assert init.status_code == 200, init.text
    upload_url = init.json()["signed_upload_url"]
    resource_id = init.json()["resource"]["id"]

    uploaded = client.put(upload_url, content=content, headers={"Content-Type": "application/pdf"})
    assert uploaded.status_code == 200, uploaded.text
    uploaded_resource = uploaded.json()["resource"]
    assert uploaded_resource["status"] == "active"
    assert uploaded_resource["metadata"]["size_bytes"] == len(content)
    assert uploaded_resource["metadata"]["sha256"] == expected_sha

    listed = client.post("/desktop/cloud/search", json={"query": "stage19"}, headers=headers)
    assert listed.status_code == 200
    assert listed.json()["items"][0]["id"] == resource_id

    prepared = client.post("/desktop/cloud/download", json={"resource_id": resource_id}, headers=headers)
    assert prepared.status_code == 200, prepared.text
    downloaded = client.get(prepared.json()["signed_download_url"])
    assert downloaded.status_code == 200
    assert downloaded.content == content
    assert hashlib.sha256(downloaded.content).hexdigest() == expected_sha


def test_signed_upload_rejects_expired_url_and_path_traversal():
    session = create_desktop_session()
    headers = {"Authorization": f"Bearer {session['access_token']}"}
    traversal = client.post(
        "/desktop/cloud/upload",
        json={"name": "bad.pdf", "mime_type": "application/pdf", "size_bytes": 10, "storage_path": "../bad.pdf"},
        headers=headers,
    )
    assert traversal.status_code == 400

    init = client.post(
        "/desktop/cloud/upload",
        json={"name": "expires.pdf", "mime_type": "application/pdf", "size_bytes": 10},
        headers=headers,
    )
    assert init.status_code == 200
    expired_url = re.sub(r"expires=\d+", "expires=1", init.json()["signed_upload_url"])
    expired = client.put(expired_url, content=b"expired")
    assert expired.status_code == 401


def test_signed_download_missing_file_returns_not_found():
    session = create_desktop_session()
    headers = {"Authorization": f"Bearer {session['access_token']}"}
    created = client.post(
        "/desktop/cloud/create",
        json={
            "name": "missing.pdf",
            "resource_type": "file",
            "mime_type": "application/pdf",
            "storage_path": "local://users/missing/missing.pdf",
        },
        headers=headers,
    )
    assert created.status_code == 200
    prepared = client.post("/desktop/cloud/download", json={"resource_id": created.json()["resource"]["id"]}, headers=headers)
    assert prepared.status_code == 200
    missing = client.get(prepared.json()["signed_download_url"])
    assert missing.status_code == 404
