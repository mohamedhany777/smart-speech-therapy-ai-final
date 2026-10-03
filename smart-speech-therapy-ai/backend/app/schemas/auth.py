import uuid

from pydantic import BaseModel, EmailStr, Field


class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=1, max_length=255)
    preferred_language: str = Field(default="en", pattern="^(en|ar)$")


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class UserOut(BaseModel):
    id: uuid.UUID
    email: EmailStr
    full_name: str | None
    preferred_language: str
    is_active: bool
    is_email_verified: bool
    roles: list[str]

    model_config = {"from_attributes": True}

    @classmethod
    def from_model(cls, user) -> "UserOut":
        return cls(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            preferred_language=user.preferred_language,
            is_active=user.is_active,
            is_email_verified=user.is_email_verified,
            roles=[r.name for r in user.roles],
        )
