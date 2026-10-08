from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.core.domain import Role


class NewUser(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    full_name: str = Field(default="", max_length=200)


class BootstrapRequest(NewUser):
    setup_code: str | None = Field(default=None, max_length=200)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(max_length=128)


class CreateUserRequest(NewUser):
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
    #: True when the web bootstrap needs a setup code; False when it is open (development).
    setup_code_required: bool
    #: False when the owner must be created with the ``matt create-owner`` command instead.
    web_bootstrap_enabled: bool
