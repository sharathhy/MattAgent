from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.domain import ROLE_RANK, Role
from app.core.security import decode_access_token
from app.db.session import get_db
from app.llm.router import ModelRouter
from app.models import User

DbSession = Annotated[Session, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]

_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    db: DbSession,
    settings: AppSettings,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    unauthorized = HTTPException(
        status.HTTP_401_UNAUTHORIZED, "Not authenticated", headers={"WWW-Authenticate": "Bearer"}
    )
    if credentials is None:
        raise unauthorized
    subject = decode_access_token(credentials.credentials, settings)
    user = db.get(User, int(subject)) if subject and subject.isdigit() else None
    if user is None or not user.is_active:
        raise unauthorized
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_role(minimum: Role) -> Callable[[User], User]:
    def checker(user: CurrentUser) -> User:
        if ROLE_RANK[Role(user.role)] < ROLE_RANK[minimum]:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Requires {minimum} role or higher")
        return user

    return checker


def get_model_router(request: Request) -> ModelRouter:
    router: ModelRouter = request.app.state.model_router
    return router


Router = Annotated[ModelRouter, Depends(get_model_router)]
Operator = Annotated[User, Depends(require_role(Role.OPERATOR))]
Admin = Annotated[User, Depends(require_role(Role.ADMIN))]
