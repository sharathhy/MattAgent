from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.core.domain import Role


class BootstrapRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    full_name: str = Field(default="", max_length=200)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(max_length=128)


class CreateUserRequest(BootstrapRequest):
    role: Role = Role.VIEWER


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105
    expires_in: int


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: str
    role: Role
    is_active: bool


class AuthStatus(BaseModel):
    bootstrap_required: bool
