from pydantic import BaseModel, EmailStr

from app.schemas.user import UserRead


class AuthCredentials(BaseModel):
    email: EmailStr
    password: str


class PasswordRecoveryRequest(BaseModel):
    email: EmailStr
    redirect_to: str | None = None


class PasswordUpdateRequest(BaseModel):
    password: str


class RefreshSessionRequest(BaseModel):
    refresh_token: str


class EmailVerificationRequest(BaseModel):
    email: EmailStr
    type: str = "signup"


class MFAEnrollRequest(BaseModel):
    friendly_name: str = "CEASER Authenticator"


class MFAChallengeRequest(BaseModel):
    factor_id: str


class MFAVerifyRequest(BaseModel):
    factor_id: str
    challenge_id: str
    code: str


class MFAUnenrollRequest(BaseModel):
    factor_id: str


class AuthSession(BaseModel):
    access_token: str | None = None
    refresh_token: str | None = None
    user: UserRead | None = None


class CurrentUser(BaseModel):
    id: str
    email: EmailStr
