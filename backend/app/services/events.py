"""Event bus: an append-only table every part of MATT writes to and the UI polls."""

from collections.abc import Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Event


def emit(db: Session, type: str, **payload: Any) -> Event:
    """Add an event to the current transaction; it is visible once the caller commits."""
    event = Event(type=type, payload=payload)
    db.add(event)
    return event


def since(db: Session, after_id: int = 0, limit: int = 100) -> Sequence[Event]:
    stmt = select(Event).order_by(Event.id.desc()).limit(limit)
    if after_id:
        stmt = select(Event).where(Event.id > after_id).order_by(Event.id).limit(limit)
        return db.scalars(stmt).all()
    return list(reversed(db.scalars(stmt).all()))
