from collections.abc import Sequence

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import Agent


def get_by_slug(db: Session, slug: str) -> Agent | None:
    return db.scalar(select(Agent).where(Agent.slug == slug))


def list_agents(
    db: Session,
    *,
    kind: str | None = None,
    department: str | None = None,
    status: str | None = None,
    search: str | None = None,
) -> Sequence[Agent]:
    stmt = select(Agent).order_by(Agent.id)
    if kind:
        stmt = stmt.where(Agent.kind == kind)
    if department:
        stmt = stmt.where(Agent.department == department)
    if status:
        stmt = stmt.where(Agent.status == status)
    if search:
        pattern = f"%{search.lower()}%"
        stmt = stmt.where(
            or_(func.lower(Agent.name).like(pattern), func.lower(Agent.description).like(pattern))
        )
    return db.scalars(stmt).all()


def count_by(db: Session, column: str) -> dict[str, int]:
    col = getattr(Agent, column)
    rows = db.execute(select(col, func.count()).group_by(col)).all()
    return {str(key): int(n) for key, n in rows}
