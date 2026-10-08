from typing import Any

from sqlalchemy.orm import Session

from app.core.logging import request_id_var
from app.models import AuditLog


def record(
    db: Session,
    *,
    actor_type: str,
    actor_id: str,
    action: str,
    target_type: str | None = None,
    target_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> AuditLog:
    """Add an audit entry to the current transaction (committed with the change it describes)."""
    entry = AuditLog(
        actor_type=actor_type,
        actor_id=actor_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        details=details or {},
        request_id=request_id_var.get(),
    )
    db.add(entry)
    return entry
