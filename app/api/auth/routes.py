from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.core.database.session import get_db
from app.core.security.dependencies import get_current_user
from app.core.security.supabase_auth import supabase_auth
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.auth import (
    AuthCredentials,
    AuthSession,
    CurrentUser,
    EmailVerificationRequest,
    MFAChallengeRequest,
    MFAEnrollRequest,
    MFAUnenrollRequest,
    MFAVerifyRequest,
    PasswordRecoveryRequest,
    PasswordUpdateRequest,
    PasswordVerificationRequest,
    ProfileUpdateRequest,
    RefreshSessionRequest,
)
from app.models.profile import Profile
from app.schemas.desktop_cloud import DesktopAuthorizeRequest, DesktopAuthorizeResponse, DesktopExchangeRequest, DesktopRefreshRequest, DesktopRevokeRequest, DesktopSessionResponse
from app.schemas.user import UserRead
from app.services.audit_service import AuditService
from app.services.desktop_auth_service import DesktopAuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/desktop-callback", response_class=HTMLResponse, include_in_schema=False)
def desktop_callback() -> HTMLResponse:
    return HTMLResponse(
        """<!doctype html>
<html><head><meta charset="utf-8"><title>Returning to CEASER</title></head>
<body style="background:#080b18;color:#fff;font:16px system-ui;display:grid;place-items:center;min-height:100vh">
<p>Returning to CEASER...</p>
<script>
const destination = "ceaser-app://bundle/auth/callback/" + location.search + location.hash;
location.replace(destination);
</script>
</body></html>"""
    )


def auth_error(exc: Exception) -> HTTPException:
    if isinstance(exc, RuntimeError):
        return HTTPException(status_code=503, detail=str(exc))
    if isinstance(exc, httpx.HTTPStatusError):
        status_code = exc.response.status_code
        try:
            payload = exc.response.json()
            detail = payload.get("msg") or payload.get("message") or payload.get("error_description") or payload.get("error") or "Authentication request failed"
        except ValueError:
            detail = "Authentication request failed"
        return HTTPException(status_code=status_code, detail=detail)
    if isinstance(exc, httpx.RequestError):
        return HTTPException(status_code=503, detail=f"Supabase Auth network error: {exc.__class__.__name__}")
    return HTTPException(status_code=503, detail="Authentication service unavailable")


def bearer_token(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Sign in required")
    return authorization.split(" ", 1)[1]


@router.post("/signup", response_model=AuthSession)
async def signup(payload: AuthCredentials, db: Annotated[Session, Depends(get_db)]) -> AuthSession:
    normalized_email = str(payload.email).strip().lower()
    if UserRepository(db).get_by_email(normalized_email):
        raise HTTPException(status_code=409, detail="Account already exists. Please sign in instead.")
    try:
        supabase_response = await supabase_auth.signup(normalized_email, payload.password)
    except Exception as exc:
        raise auth_error(exc) from exc

    supabase_user = supabase_response.get("user") or {}
    user = UserRepository(db).get_or_create(email=normalized_email, user_id=supabase_user.get("id"))
    db.commit()
    db.refresh(user)
    AuditService(db).record(user_id=user.id, action="login", resource_type="auth", resource_id=user.id, metadata={"event": "signup"})
    session = supabase_response.get("session") or {}
    return AuthSession(access_token=session.get("access_token"), refresh_token=session.get("refresh_token"), user=UserRead.model_validate(user))


@router.post("/login", response_model=AuthSession)
async def login(payload: AuthCredentials, db: Annotated[Session, Depends(get_db)]) -> AuthSession:
    try:
        supabase_response = await supabase_auth.login(payload.email, payload.password)
    except Exception as exc:
        raise auth_error(exc) from exc

    supabase_user = supabase_response.get("user") or {}
    user = UserRepository(db).get_or_create(email=payload.email, user_id=supabase_user.get("id"))
    db.commit()
    db.refresh(user)
    AuditService(db).record(user_id=user.id, action="login", resource_type="auth", resource_id=user.id)
    return AuthSession(
        access_token=supabase_response.get("access_token"),
        refresh_token=supabase_response.get("refresh_token"),
        user=UserRead.model_validate(user),
    )


@router.post("/logout")
def logout() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/sign-out")
def sign_out() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/refresh", response_model=AuthSession)
async def refresh_session(payload: RefreshSessionRequest, db: Annotated[Session, Depends(get_db)]) -> AuthSession:
    try:
        supabase_response = await supabase_auth.refresh_session(payload.refresh_token)
    except Exception as exc:
        raise auth_error(exc) from exc

    supabase_user = supabase_response.get("user") or {}
    email = supabase_user.get("email")
    if not email:
        access_token = supabase_response.get("access_token")
        if not access_token:
            raise HTTPException(status_code=401, detail="Invalid session")
        try:
            user_response = await supabase_auth.get_user(access_token)
            supabase_user = user_response
            email = supabase_user.get("email")
        except Exception as exc:
            raise auth_error(exc) from exc
    if not email:
        raise HTTPException(status_code=401, detail="Invalid session")

    user = UserRepository(db).get_or_create(email=email, user_id=supabase_user.get("id"))
    db.commit()
    db.refresh(user)
    return AuthSession(
        access_token=supabase_response.get("access_token"),
        refresh_token=supabase_response.get("refresh_token") or payload.refresh_token,
        user=UserRead.model_validate(user),
    )


@router.post("/desktop/authorize", response_model=DesktopAuthorizeResponse)
def authorize_desktop(
    payload: DesktopAuthorizeRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    result = DesktopAuthService(db).authorize(user, payload)
    AuditService(db).record(user_id=user.id, action="desktop_authorized", resource_type="desktop", resource_id=payload.device_id, metadata={"platform": payload.platform})
    return result


@router.post("/desktop/exchange", response_model=DesktopSessionResponse)
def exchange_desktop(payload: DesktopExchangeRequest, db: Annotated[Session, Depends(get_db)]) -> dict:
    return DesktopAuthService(db).exchange(payload)


@router.post("/desktop/refresh", response_model=DesktopSessionResponse)
def refresh_desktop(payload: DesktopRefreshRequest, db: Annotated[Session, Depends(get_db)]) -> dict:
    return DesktopAuthService(db).refresh(payload.refresh_token, payload.device_id)


@router.post("/desktop/revoke")
def revoke_desktop(
    payload: DesktopRevokeRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, str]:
    DesktopAuthService(db).revoke(user, refresh_token=payload.refresh_token, device_id=payload.device_id)
    AuditService(db).record(user_id=user.id, action="desktop_revoked", resource_type="desktop", resource_id=payload.device_id or user.id)
    return {"status": "ok"}


@router.post("/password/recover")
async def recover_password(payload: PasswordRecoveryRequest) -> dict[str, str]:
    try:
        await supabase_auth.recover_password(str(payload.email), payload.redirect_to)
    except Exception as exc:
        raise auth_error(exc) from exc
    return {"status": "ok", "message": "Password recovery email sent if the account exists."}


@router.post("/password/update")
async def update_password(
    payload: PasswordUpdateRequest,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, str]:
    try:
        access_token = bearer_token(authorization)
        user = await supabase_auth.get_user(access_token)
        email = user.get("email")
        if not email:
            raise HTTPException(status_code=401, detail="Sign in required")
        await supabase_auth.login(email, payload.current_password)
        password = payload.password
        if (
            len(password) < 8
            or not any(character.isupper() for character in password)
            or not any(character.islower() for character in password)
            or not any(character.isdigit() for character in password)
            or not any(not character.isalnum() for character in password)
        ):
            raise HTTPException(status_code=422, detail="New password does not meet the security requirements")
        await supabase_auth.update_password(access_token, password)
    except HTTPException:
        raise
    except Exception as exc:
        raise auth_error(exc) from exc
    return {"status": "ok", "message": "Password updated."}


@router.post("/password/verify")
async def verify_password(
    payload: PasswordVerificationRequest,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, str]:
    try:
        user = await supabase_auth.get_user(bearer_token(authorization))
        email = user.get("email")
        if not email:
            raise HTTPException(status_code=401, detail="Sign in required")
        await supabase_auth.login(email, payload.password)
    except HTTPException:
        raise
    except Exception as exc:
        raise auth_error(exc) from exc
    return {"status": "ok", "message": "Password verified."}


@router.post("/email/resend-verification")
async def resend_verification(payload: EmailVerificationRequest) -> dict[str, str]:
    try:
        await supabase_auth.resend_verification(str(payload.email), payload.type)
    except Exception as exc:
        raise auth_error(exc) from exc
    return {"status": "ok", "message": "Verification email sent if the account exists."}


@router.post("/mfa/enroll")
async def enroll_mfa(
    payload: MFAEnrollRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    authorization: Annotated[str | None, Header()] = None,
) -> dict:
    try:
        result = await supabase_auth.enroll_totp(bearer_token(authorization), payload.friendly_name)
    except Exception as exc:
        raise auth_error(exc) from exc
    AuditService(db).record(user_id=user.id, action="mfa_enroll_started", resource_type="auth", resource_id=user.id)
    return result


@router.get("/mfa/factors")
async def list_mfa_factors(
    authorization: Annotated[str | None, Header()] = None,
    user: Annotated[User, Depends(get_current_user)] = None,
) -> dict:
    try:
        return await supabase_auth.list_factors(bearer_token(authorization))
    except Exception as exc:
        raise auth_error(exc) from exc


@router.post("/mfa/challenge")
async def challenge_mfa(
    payload: MFAChallengeRequest,
    authorization: Annotated[str | None, Header()] = None,
    user: Annotated[User, Depends(get_current_user)] = None,
) -> dict:
    try:
        return await supabase_auth.challenge_factor(bearer_token(authorization), payload.factor_id)
    except Exception as exc:
        raise auth_error(exc) from exc


@router.post("/mfa/verify")
async def verify_mfa(
    payload: MFAVerifyRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    authorization: Annotated[str | None, Header()] = None,
) -> dict:
    try:
        result = await supabase_auth.verify_factor(bearer_token(authorization), payload.factor_id, payload.challenge_id, payload.code)
    except Exception as exc:
        raise auth_error(exc) from exc
    AuditService(db).record(user_id=user.id, action="mfa_verified", resource_type="auth", resource_id=user.id)
    return result


@router.post("/mfa/unenroll")
async def unenroll_mfa(
    payload: MFAUnenrollRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    authorization: Annotated[str | None, Header()] = None,
) -> dict:
    try:
        result = await supabase_auth.unenroll_factor(bearer_token(authorization), payload.factor_id)
    except Exception as exc:
        raise auth_error(exc) from exc
    AuditService(db).record(user_id=user.id, action="mfa_unenrolled", resource_type="auth", resource_id=user.id)
    return result


@router.get("/me", response_model=CurrentUser)
def me(user: Annotated[User, Depends(get_current_user)]) -> CurrentUser:
    return current_user_payload(user)


@router.get("/session", response_model=CurrentUser)
def session(user: Annotated[User, Depends(get_current_user)]) -> CurrentUser:
    return current_user_payload(user)


@router.patch("/profile", response_model=CurrentUser)
def update_profile(
    payload: ProfileUpdateRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> CurrentUser:
    display_name = " ".join(payload.display_name.split()).strip()
    if not display_name or len(display_name) > 255:
        raise HTTPException(status_code=422, detail="Display name must be between 1 and 255 characters")
    profile = user.profile
    if profile is None:
        profile = Profile(user=user)
        db.add(profile)
    profile.display_name = display_name
    if payload.use_case is not None:
        profile.use_case = payload.use_case.strip()[:50] or None
    if payload.onboarding_data is not None:
        profile.onboarding_data = payload.onboarding_data
    if payload.onboarding_completed is not None:
        profile.onboarding_completed = payload.onboarding_completed
    db.commit()
    db.refresh(user)
    AuditService(db).record(
        user_id=user.id,
        action="profile_updated",
        resource_type="profile",
        resource_id=profile.id,
        metadata={"fields": [
            field for field, supplied in {
                "display_name": True,
                "use_case": payload.use_case is not None,
                "onboarding_data": payload.onboarding_data is not None,
                "onboarding_completed": payload.onboarding_completed is not None,
            }.items() if supplied
        ]},
    )
    return current_user_payload(user)


def current_user_payload(user: User) -> CurrentUser:
    display_name = user.profile.display_name.strip() if user.profile and user.profile.display_name else None
    return CurrentUser(
        id=user.id,
        email=user.email,
        display_name=display_name,
        use_case=user.profile.use_case if user.profile else None,
        onboarding_data=user.profile.onboarding_data or {} if user.profile else {},
        onboarding_completed=bool(user.profile and user.profile.onboarding_completed),
    )
