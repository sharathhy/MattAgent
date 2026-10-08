"""Autopilot: on a schedule the CEO picks the next most valuable action and queues it.

It only does work that stays inside MATT: finding and auditing businesses, scoring
opportunities, drafting outreach (which waits in Approvals), and the daily report. It never
sends, spends or publishes. Paid models stay inside the INR budgets via the model router.
"""

import itertools
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.domain import ACTIVE_TASK_STATUSES, TaskStatus
from app.llm.router import ModelRouter
from app.models import Autopilot, Business, Knowledge, Lead, Task, User
from app.plugins.business_discovery import CATEGORIES
from app.services import audit, events, tasks
from app.services.errors import ServiceError

ACTOR = "autopilot"
#: Starting targets until the owner sets their own (an assumption, shown in the UI).
DEFAULT_CITIES = ["Bengaluru", "Mysuru"]
DEFAULT_CATEGORIES = ["clinics", "dentists", "gyms", "salons", "restaurants"]
RESEARCH_FOCUS = [
    "AI services that local businesses in India will pay for",
    "AI SaaS products a solo founder in India can build and sell within 60 days",
]
MIN_INTERVAL, MAX_INTERVAL = 10, 1440


def get(db: Session) -> Autopilot:
    row = db.scalar(select(Autopilot).limit(1))
    if row is None:
        row = Autopilot(
            enabled=False, cities=list(DEFAULT_CITIES), categories=list(DEFAULT_CATEGORIES),
            interval_minutes=30, daily_outreach_drafts=5, cursor=0,
        )  # fmt: skip
        db.add(row)
        db.commit()
    return row


def update(db: Session, user: User, changes: dict[str, Any]) -> Autopilot:
    row = get(db)
    if "categories" in changes:
        unknown = [c for c in changes["categories"] if c not in CATEGORIES]
        if unknown:
            raise ServiceError(f"Unknown categories: {', '.join(unknown)}")
    if "interval_minutes" in changes and not (
        MIN_INTERVAL <= changes["interval_minutes"] <= MAX_INTERVAL
    ):
        raise ServiceError(f"Interval must be {MIN_INTERVAL}-{MAX_INTERVAL} minutes")
    for key, value in changes.items():
        setattr(row, key, value)
    if changes.get("enabled"):
        row.next_cycle_at = datetime.now(UTC)  # start now
    row.updated_by = str(user.id)
    audit.record(
        db, actor_type="user", actor_id=str(user.id), action="autopilot.updated",
        target_type="autopilot", target_id=str(row.id),
        details={k: str(v) for k, v in changes.items()},
    )  # fmt: skip
    events.emit(db, "autopilot.updated", enabled=row.enabled, by=str(user.id))
    db.commit()
    return row


def _day_start(tz: str) -> datetime:
    local = datetime.now(ZoneInfo(tz)).replace(hour=0, minute=0, second=0, microsecond=0)
    return local.astimezone(UTC)


def _count(db: Session, *where: Any) -> int:
    return int(db.scalar(select(func.count()).select_from(Task).where(*where)) or 0)


def choose(db: Session, router: ModelRouter, row: Autopilot) -> tuple[str, dict[str, Any], str]:
    """Return (objective, task input, reason) for the next most valuable action."""
    tz = router.settings.timezone
    today = _day_start(tz)
    has_report = db.scalar(
        select(Knowledge.id).where(Knowledge.kind == "report", Knowledge.created_at >= today)
    )
    if has_report is None:
        return ("Write today's CEO report", {"workflow": "daily_report", "params": {}},
                "First cycle of the day: report where the business stands.")  # fmt: skip

    if router.available:
        drafted = _count(
            db, Task.created_by == ACTOR, Task.objective.startswith("Draft outreach"),
            Task.created_at >= today,
        )  # fmt: skip
        if drafted < row.daily_outreach_drafts:
            candidates = db.scalars(
                select(Lead).join(Business).where(
                    Lead.status == "new", Lead.outreach_draft.is_(None),
                    Business.outreach_status.is_(None),
                    (Business.public_email.is_not(None)) | (Business.public_phone.is_not(None)),
                ).order_by(Business.opportunity_score.desc().nulls_last()).limit(1)
            ).all()  # fmt: skip
            if candidates:
                lead = candidates[0]
                return (f"Draft outreach for {lead.business.name}",
                        {"workflow": "draft_outreach", "params": {"lead_id": lead.id}},
                        "Best-scored lead with a public contact has no pitch yet; "
                        "the draft will wait for your approval.")  # fmt: skip
        researched = _count(
            db, Task.created_by == ACTOR, Task.objective.startswith("Research"),
            Task.created_at >= datetime.now(UTC) - timedelta(days=1),
        )  # fmt: skip
        if not researched:
            focus = RESEARCH_FOCUS[row.cursor % len(RESEARCH_FOCUS)]
            return (f"Research opportunities: {focus}",
                    {"workflow": "opportunity_research", "params": {"focus": focus}},
                    "No opportunity research in the last 24 hours.")  # fmt: skip

    pairs = list(itertools.product(row.cities or DEFAULT_CITIES,
                                   row.categories or DEFAULT_CATEGORIES))  # fmt: skip
    city, category = pairs[row.cursor % len(pairs)]
    row.cursor += 1
    return (f"Find {category} in {city} and rank website opportunities",
            {"workflow": "website_opportunities",
             "params": {"city": city, "category": category, "limit": 10}},
            "Keep the lead pipeline full: next city and niche in rotation.")  # fmt: skip


def tick(db: Session, router: ModelRouter, *, force: bool = False) -> Task | None:
    """Queue one autopilot action if one is due. Safe to call often."""
    row = get(db)
    now = datetime.now(UTC)
    if not row.enabled and not force:
        return None
    due = row.next_cycle_at
    if due is not None and due.tzinfo is None:
        due = due.replace(tzinfo=UTC)
    if not force and due is not None and now < due:
        return None
    busy = _count(db, Task.created_by == ACTOR,
                  Task.status.in_([TaskStatus.QUEUED, TaskStatus.RUNNING]))  # fmt: skip
    if busy:
        row.next_cycle_at = now + timedelta(minutes=1)
        db.commit()
        return None
    objective, task_input, reason = choose(db, router, row)
    task = tasks.create(db, kind="workflow", objective=objective, input=task_input,
                        created_by=ACTOR, priority=6, commit=False)  # fmt: skip
    row.last_cycle_at, row.last_action = now, objective
    row.next_cycle_at = now + timedelta(minutes=row.interval_minutes)
    events.emit(db, "autopilot.cycle", task_id=task.id, action=objective, reason=reason)
    db.commit()
    return task


def status(db: Session, router: ModelRouter) -> dict[str, Any]:
    row = get(db)
    today = _day_start(router.settings.timezone)
    recent = db.scalars(
        select(Task).where(Task.created_by == ACTOR).order_by(Task.id.desc()).limit(10)
    ).all()
    report = db.scalar(
        select(Knowledge).where(Knowledge.kind == "report").order_by(Knowledge.id.desc()).limit(1)
    )
    return {
        "enabled": row.enabled,
        "cities": row.cities,
        "categories": row.categories,
        "interval_minutes": row.interval_minutes,
        "daily_outreach_drafts": row.daily_outreach_drafts,
        "last_cycle_at": row.last_cycle_at,
        "next_cycle_at": row.next_cycle_at if row.enabled else None,
        "last_action": row.last_action,
        "cycles_today": _count(db, Task.created_by == ACTOR, Task.created_at >= today),
        "active": _count(db, Task.created_by == ACTOR, Task.status.in_(list(ACTIVE_TASK_STATUSES))),
        "ai_model_available": router.available,
        "available_categories": list(CATEGORIES),
        "recent": [
            {
                "task_id": t.id,
                "action": t.objective,
                "status": t.status,
                "result": t.output or t.error,
                "created_at": t.created_at,
            }
            for t in recent
        ],
        "latest_report": (
            {"title": report.title, "content": report.content, "created_at": report.created_at}
            if report
            else None
        ),
    }
