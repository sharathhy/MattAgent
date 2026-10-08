"""Earnings from the ledger. Only amounts a person recorded count; nothing is projected."""

from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.domain import RevenueCategory
from app.models import Agent, LedgerEntry, User
from app.services import audit, events
from app.services.errors import NotFoundError


def today(tz: str) -> date:
    return datetime.now(ZoneInfo(tz)).date()


def _sum(db: Session, kind: str, since: date | None = None, until: date | None = None) -> float:
    stmt = select(func.coalesce(func.sum(LedgerEntry.amount_inr), 0)).where(
        LedgerEntry.kind == kind
    )
    if since:
        stmt = stmt.where(LedgerEntry.occurred_on >= since)
    if until:
        stmt = stmt.where(LedgerEntry.occurred_on <= until)
    return float(db.scalar(stmt) or 0)


def sync_agent_revenue(db: Session, slug: str | None) -> None:
    """Keep ``Agent.revenue_contribution`` equal to the revenue attributed to it."""
    if not slug:
        return
    agent = db.scalar(select(Agent).where(Agent.slug == slug))
    if agent is not None:
        agent.revenue_contribution = Decimal(str(_sum_agent(db, slug)))


def _sum_agent(db: Session, slug: str) -> float:
    stmt = select(func.coalesce(func.sum(LedgerEntry.amount_inr), 0)).where(
        LedgerEntry.kind == "revenue", LedgerEntry.agent_slug == slug
    )
    return float(db.scalar(stmt) or 0)


def check_agent(db: Session, slug: str | None) -> None:
    if slug and db.scalar(select(Agent.id).where(Agent.slug == slug)) is None:
        raise NotFoundError(f"No agent called {slug!r}")


def record(
    db: Session,
    user: User,
    *,
    kind: str,
    amount_inr: Decimal,
    description: str,
    occurred_on: date,
    category: str = RevenueCategory.OTHER,
    recurring: bool = False,
    customer_id: int | None = None,
    product_id: int | None = None,
    agent_slug: str | None = None,
) -> LedgerEntry:
    check_agent(db, agent_slug)
    entry = LedgerEntry(
        kind=kind, amount_inr=amount_inr, category=category, description=description,
        occurred_on=occurred_on, recurring=recurring, customer_id=customer_id,
        product_id=product_id, agent_slug=agent_slug, recorded_by=str(user.id),
    )  # fmt: skip
    db.add(entry)
    db.flush()
    sync_agent_revenue(db, agent_slug)
    audit.record(
        db, actor_type="user", actor_id=str(user.id), action="ledger_entries.created",
        target_type="ledger_entries", target_id=str(entry.id),
        details={"kind": kind, "amount_inr": str(amount_inr), "agent": agent_slug},
    )  # fmt: skip
    events.emit(db, "ledger.recorded", kind=kind, amount_inr=str(amount_inr),
                category=category, agent=agent_slug)  # fmt: skip
    db.commit()
    return entry


def summary(db: Session, tz: str, days: int = 30) -> dict[str, Any]:
    now = today(tz)
    month_start = now.replace(day=1)
    week_start = now - timedelta(days=6)
    first = now - timedelta(days=days - 1)

    daily: dict[date, dict[str, float]] = {
        first + timedelta(days=i): {"revenue": 0.0, "expense": 0.0} for i in range(days)
    }
    for day, kind, amount in db.execute(
        select(LedgerEntry.occurred_on, LedgerEntry.kind, func.sum(LedgerEntry.amount_inr))
        .where(LedgerEntry.occurred_on >= first, LedgerEntry.occurred_on <= now)
        .group_by(LedgerEntry.occurred_on, LedgerEntry.kind)
    ):
        daily[day][kind] = float(amount or 0)

    streams: dict[str, dict[str, float]] = defaultdict(lambda: {"month_inr": 0.0, "total_inr": 0.0})
    agents: dict[str, dict[str, Any]] = {}
    for e in db.scalars(select(LedgerEntry).where(LedgerEntry.kind == "revenue")):
        value = float(e.amount_inr)
        streams[e.category]["total_inr"] += value
        if e.occurred_on >= month_start:
            streams[e.category]["month_inr"] += value
        if e.agent_slug:
            a = agents.setdefault(
                e.agent_slug,
                {"slug": e.agent_slug, "today_inr": 0.0, "month_inr": 0.0, "total_inr": 0.0,
                 "last_earned_on": e.occurred_on},
            )  # fmt: skip
            a["total_inr"] += value
            a["month_inr"] += value if e.occurred_on >= month_start else 0
            a["today_inr"] += value if e.occurred_on == now else 0
            a["last_earned_on"] = max(a["last_earned_on"], e.occurred_on)
    names: dict[str, str] = {
        slug: name
        for slug, name in db.execute(
            select(Agent.slug, Agent.name).where(Agent.slug.in_(list(agents)))
        )
    }
    for a in agents.values():
        a["name"] = names.get(a["slug"], a["slug"])
        a["last_earned_on"] = a["last_earned_on"].isoformat()

    return {
        "truth": "fact",
        "timezone": tz,
        "date": now.isoformat(),
        "today_inr": _sum(db, "revenue", now, now),
        "expenses_today_inr": _sum(db, "expense", now, now),
        "week_inr": _sum(db, "revenue", week_start, now),
        "month_inr": _sum(db, "revenue", month_start, now),
        "total_inr": _sum(db, "revenue"),
        "daily": [
            {"day": d.isoformat(), "revenue_inr": v["revenue"], "expense_inr": v["expense"]}
            for d, v in sorted(daily.items())
        ],
        "by_stream": sorted(
            ({"category": c, **v} for c, v in streams.items()),
            key=lambda s: s["total_inr"],
            reverse=True,
        ),
        "earning_agents": sorted(agents.values(), key=lambda a: a["total_inr"], reverse=True),
    }
