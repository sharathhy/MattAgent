from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import User


def get_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(func.lower(User.email) == email.lower()))


def count(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(User)) or 0
