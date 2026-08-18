from pydantic import BaseModel, EmailStr, Field

from app.schemas.user import UserRead


class AuthCredentials(BaseModel):
    email: EmailStr
    password: str
    referral_code: str | None = Field(default=None, min_length=4, max_length=40)


class PasswordRecoveryRequest(BaseModel):
    email: EmailStr
    redirect_to: str | None = None


class PasswordUpdateRequest(BaseModel):
    current_password: str
    password: str


class PasswordVerificationRequest(BaseModel):
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
    display_name: str | None = None
    use_case: str | None = None
    onboarding_data: dict = Field(default_factory=dict)
    onboarding_completed: bool = False


class ProfileUpdateRequest(BaseModel):
    display_name: str
    use_case: str | None = None
    onboarding_data: dict | None = None
    onboarding_completed: bool | None = None
