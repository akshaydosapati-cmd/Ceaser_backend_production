from pydantic import BaseModel, EmailStr

from app.schemas.common import TimestampedModel


class UserCreate(BaseModel):
    email: EmailStr


class UserRead(TimestampedModel):
    email: EmailStr


class ProfileRead(BaseModel):
    id: str
    user_id: str
    display_name: str | None = None
    avatar_url: str | None = None

    model_config = {"from_attributes": True}
