from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.deps import AppSettings, CurrentUser, DbSession, require_role
from app.core.domain import Role
from app.core.rate_limit import RateLimiter
from app.core.security import create_access_token
from app.models import User
from app.repositories import users as user_repo
from app.schemas.auth import (
    AuthStatus,
    BootstrapRequest,
    CreateUserRequest,
    LoginRequest,
    TokenResponse,
    UserOut,
)
from app.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


def _login_limiter(request: Request) -> RateLimiter:
    limiter: RateLimiter = request.app.state.login_limiter
    return limiter


@router.get("/status", response_model=AuthStatus)
def auth_status(db: DbSession) -> AuthStatus:
    return AuthStatus(bootstrap_required=user_repo.count(db) == 0)


@router.post("/bootstrap", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def bootstrap(body: BootstrapRequest, db: DbSession) -> User:
    return auth_service.bootstrap_owner(
        db, email=body.email, password=body.password, full_name=body.full_name
    )


@router.post("/login", response_model=TokenResponse)
def login(
    body: LoginRequest,
    request: Request,
    db: DbSession,
    settings: AppSettings,
    limiter: Annotated[RateLimiter, Depends(_login_limiter)],
) -> TokenResponse:
    client = request.client.host if request.client else "unknown"
    if not limiter.allow(f"{client}:{body.email.lower()}"):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many login attempts; try later")
    user = auth_service.authenticate(db, body.email, body.password)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    return TokenResponse(
        access_token=create_access_token(str(user.id), settings),
        expires_in=settings.access_token_minutes * 60,
    )


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> User:
    return user


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    body: CreateUserRequest,
    db: DbSession,
    actor: Annotated[User, Depends(require_role(Role.OWNER))],
) -> User:
    if body.role == Role.OWNER:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "There is exactly one owner")
    return auth_service.create_user(
        db, email=body.email, password=body.password, full_name=body.full_name,
        role=body.role, created_by=str(actor.id),
    )  # fmt: skip
