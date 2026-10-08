from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.api.deps import DbSession, require_role
from app.core.domain import Role
from app.models import AuditLog, User
from app.schemas.audit import AuditLogOut

router = APIRouter(prefix="/audit-logs", tags=["audit"])


@router.get("", response_model=list[AuditLogOut])
def list_audit_logs(
    db: DbSession,
    _: Annotated[User, Depends(require_role(Role.ADMIN))],
    action: str | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[AuditLog]:
    stmt = select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    return list(db.scalars(stmt))
