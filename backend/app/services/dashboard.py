"""Live numbers for the Command Center and Analytics. Everything is computed from stored
records; nothing is projected or made up."""

from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.domain import ApprovalStatus, TaskStatus
from app.llm.router import ModelRouter
from app.models import (
    Agent,
    Approval,
    Business,
    Lead,
    LedgerEntry,
    ModelUsage,
    Opportunity,
    Task,
)
from app.services import earnings


def _num(v: Any) -> float:
    return float(v or 0)


def _ledger_total(db: Session, kind: str, since: date | None = None) -> float:
    stmt = select(func.coalesce(func.sum(LedgerEntry.amount_inr), 0)).where(
        LedgerEntry.kind == kind
    )
    if since:
        stmt = stmt.where(LedgerEntry.occurred_on >= since)
    return _num(db.scalar(stmt))


def _group(db: Session, column: Any) -> dict[str, int]:
    return {str(k): int(v) for k, v in db.execute(select(column, func.count()).group_by(column))}


def overview(db: Session, router: ModelRouter, settings: Settings) -> dict[str, Any]:
    now = datetime.now(UTC)
    month_start = earnings.today(settings.timezone).replace(day=1)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    tasks_by_status = _group(db, Task.status)
    agents_active = db.scalar(
        select(func.count()).select_from(Agent).where(Agent.tasks_completed > 0)
    )
    top_agents = db.scalars(
        select(Agent)
        .where(Agent.tasks_completed > 0)
        .order_by(Agent.tasks_completed.desc())
        .limit(5)
    ).all()
    recent_tasks = db.scalars(select(Task).order_by(Task.id.desc()).limit(8)).all()
    top_opps = db.scalars(select(Opportunity).order_by(Opportunity.score.desc()).limit(5)).all()
    revenue_month = _ledger_total(db, "revenue", month_start)
    expense_month = _ledger_total(db, "expense", month_start)
    earned = earnings.summary(db, settings.timezone)
    return {
        "earnings": earned,
        "revenue": {
            "truth": "fact",
            "today_inr": earned["today_inr"],
            "week_inr": earned["week_inr"],
            "earning_skills": [
                {
                    "slug": a["slug"],
                    "name": a["name"],
                    "revenue_inr": a["total_inr"],
                    "revenue_today_inr": a["today_inr"],
                    "revenue_month_inr": a["month_inr"],
                }
                for a in earned["earning_agents"]
            ],
            "month_inr": revenue_month,
            "total_inr": _ledger_total(db, "revenue"),
            "expenses_month_inr": expense_month,
            "profit_month_inr": revenue_month - expense_month,
            "entries": int(db.scalar(select(func.count()).select_from(LedgerEntry)) or 0),
        },
        "tasks": {
            "by_status": tasks_by_status,
            "active": sum(tasks_by_status.get(s, 0) for s in ("queued", "running")),
            "recent": [
                {
                    "id": t.id,
                    "objective": t.objective[:160],
                    "status": t.status,
                    "agent": t.agent.slug if t.agent else None,
                    "kind": t.kind,
                    "created_at": t.created_at.isoformat(),
                }
                for t in recent_tasks
            ],
        },
        "approvals_pending": int(
            db.scalar(
                select(func.count())
                .select_from(Approval)
                .where(Approval.status == ApprovalStatus.PENDING)
            )
            or 0
        ),
        "pipeline": {
            "businesses": int(db.scalar(select(func.count()).select_from(Business)) or 0),
            "audited": int(
                db.scalar(
                    select(func.count())
                    .select_from(Business)
                    .where(Business.audited_at.is_not(None))
                )
                or 0
            ),
            "leads_by_status": _group(db, Lead.status),
            "pipeline_value_inr": {
                "truth": "assumption",
                "min": _num(db.scalar(select(func.sum(Lead.estimated_value_min_inr)))),
                "max": _num(db.scalar(select(func.sum(Lead.estimated_value_max_inr)))),
            },
        },
        "workforce": {
            "agents": int(db.scalar(select(func.count()).select_from(Agent)) or 0),
            "agents_with_work": int(agents_active or 0),
            "top": [
                {
                    "slug": a.slug,
                    "name": a.name,
                    "tasks_completed": a.tasks_completed,
                    "success_rate": a.success_rate,
                }
                for a in top_agents
            ],
        },
        "ai": {
            "model_available": router.available,
            "spent_today_inr": float(router.spent_inr(db, day_start)),
            "spent_month_inr": float(router.spent_inr(db, now - timedelta(days=30))),
            "daily_budget_inr": settings.daily_ai_budget_inr,
            "monthly_budget_inr": settings.monthly_ai_budget_inr,
            "calls_today": int(
                db.scalar(
                    select(func.count())
                    .select_from(ModelUsage)
                    .where(ModelUsage.created_at >= day_start)
                )
                or 0
            ),
        },
        "opportunities": [
            {"id": o.id, "title": o.title, "score": o.score, "truth": o.truth} for o in top_opps
        ],
    }


def analytics(db: Session) -> dict[str, Any]:
    since = datetime.now(UTC) - timedelta(days=14)
    day = func.date(Task.created_at)
    tasks_daily = [
        {"day": str(d), "total": int(t), "succeeded": int(s or 0), "failed": int(f or 0)}
        for d, t, s, f in db.execute(
            select(
                day,
                func.count(),
                func.sum(case((Task.status == TaskStatus.SUCCEEDED, 1), else_=0)),
                func.sum(case((Task.status == TaskStatus.FAILED, 1), else_=0)),
            )
            .where(Task.created_at >= since)
            .group_by(day)
            .order_by(day)
        )
    ]
    monthly: dict[tuple[str, str, str], float] = {}
    for e in db.scalars(select(LedgerEntry)):
        key = (e.occurred_on.strftime("%Y-%m"), e.kind, e.category)
        monthly[key] = monthly.get(key, 0.0) + float(e.amount_inr)
    ledger = [
        {"month": m, "kind": k, "category": c, "amount_inr": a}
        for (m, k, c), a in sorted(monthly.items())
    ]
    models = [
        {
            "provider": p,
            "model": m,
            "calls": int(n),
            "failures": int(f or 0),
            "tokens": int(t or 0),
            "cost_inr": _num(c),
            "avg_latency_ms": int(lat or 0),
        }
        for p, m, n, f, t, c, lat in db.execute(
            select(
                ModelUsage.provider,
                ModelUsage.model,
                func.count(),
                func.sum(case((ModelUsage.success.is_(False), 1), else_=0)),
                func.sum(ModelUsage.prompt_tokens + ModelUsage.completion_tokens),
                func.sum(ModelUsage.cost_inr),
                func.avg(ModelUsage.latency_ms),
            ).group_by(ModelUsage.provider, ModelUsage.model)
        )
    ]
    agents = [
        {
            "slug": a.slug,
            "name": a.name,
            "completed": a.tasks_completed,
            "failed": a.tasks_failed,
            "success_rate": a.success_rate,
        }
        for a in db.scalars(
            select(Agent)
            .where((Agent.tasks_completed + Agent.tasks_failed) > 0)
            .order_by((Agent.tasks_completed + Agent.tasks_failed).desc())
            .limit(20)
        )
    ]
    funnel = _group(db, Lead.status)
    scores = [
        s
        for s in db.scalars(
            select(Business.website_score).where(Business.website_score.is_not(None))
        )
        if s is not None
    ]
    return {
        "tasks_daily": tasks_daily,
        "ledger_monthly": ledger,
        "models": models,
        "agents": agents,
        "lead_funnel": funnel,
        "website_scores": {
            "truth": "estimate",
            "count": len(scores),
            "average": round(sum(scores) / len(scores), 1) if scores else None,
            "below_50": sum(1 for s in scores if s < 50),
        },
        "generated_at": datetime.now(UTC).isoformat(),
    }
