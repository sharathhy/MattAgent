"""Free Model Scout: keeps MATT on the best free AI models it is allowed to use.

Run by the Cost Optimization meta-skill on a schedule. For every curated free-tier service it
checks whether a key is connected, reads that service's model list, picks the best free model
and switches the router to it. It records health and the last 24 hours of calls. It cannot
sign up for accounts or create keys, so for a useful service that is not connected it asks the
owner once, in Approvals, to add the key in Render. It never pays for anything.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core.domain import ApprovalStatus, RiskLevel
from app.llm.free_sources import FREE_SOURCES, FreeSource
from app.llm.providers import DiscoveringProvider, ProviderError
from app.llm.router import ModelRouter
from app.models import Approval, ModelSource, ModelUsage, User
from app.services import events

AGENT = "meta-cost-optimization"
EVERY = timedelta(hours=6)


def _row(db: Session, slug: str) -> ModelSource:
    row = db.scalar(select(ModelSource).where(ModelSource.slug == slug))
    if row is None:
        row = ModelSource(slug=slug, status="not_connected", free_models=0)
        db.add(row)
    return row


def _asked(db: Session, slug: str) -> bool:
    rows = db.scalars(select(Approval).where(Approval.kind == "setup")).all()
    return any(a.details.get("provider") == slug for a in rows)


def _ask_owner(db: Session, source: FreeSource) -> Approval:
    approval = Approval(
        agent_slug=AGENT, kind="setup", risk_level=RiskLevel.LOW, status=ApprovalStatus.PENDING,
        action=f"Connect the free {source.name} tier: add {source.env_var} in Render",
        details={
            "provider": source.slug, "env_var": source.env_var, "signup_url": source.signup_url,
            "free_limits": f"ESTIMATE: {source.free_limits}", "note": source.note,
            "why": "RECOMMENDATION: another free service lets MATT keep working when one free "
            "tier hits its daily limit. MATT cannot create accounts or keys itself. Create a "
            "free key (no card, keep billing off), add it in Render, then approve this.",
        },
    )  # fmt: skip
    db.add(approval)
    events.emit(db, "scout.asked", provider=source.slug, env_var=source.env_var)
    return approval


def scan(db: Session, router: ModelRouter) -> list[dict[str, Any]]:
    """Check every free source, switch each connected one to its best free model, and ask the
    owner to connect the most useful missing one (one open request at a time)."""
    now = datetime.now(UTC)
    for source in FREE_SOURCES:
        row = _row(db, source.slug)
        provider = router.provider(source.slug)
        row.checked_at, row.error = now, None
        if provider is None:
            row.status, row.model, row.free_models = "not_connected", None, 0
            continue
        if not isinstance(provider, DiscoveringProvider):
            row.status, row.model = "ok", provider.spec.model
            continue
        try:
            models = provider.list_models()
        except ProviderError as exc:
            row.status, row.error = "error", str(exc)[:500]
            continue
        best = provider.pick(models)
        row.free_models = len(provider.free_models(models))
        if best is None:
            row.status, row.model = "no_free_model", provider.spec.model or None
            continue
        if best != provider.spec.model:
            events.emit(db, "scout.switched", provider=source.slug, old=provider.spec.model,
                        new=best)  # fmt: skip
            provider.use_model(best)
        row.status, row.model = "ok", best
    open_ask = (Approval.kind == "setup", Approval.status == ApprovalStatus.PENDING)
    pending = db.scalar(select(Approval.id).where(*open_ask))
    if pending is None and db.scalar(select(User.id).limit(1)) is not None:
        missing = next(
            (s for s in FREE_SOURCES
             if s.recommend and router.provider(s.slug) is None and not _asked(db, s.slug)),
            None,
        )  # fmt: skip
        if missing is not None:
            _ask_owner(db, missing)
    events.emit(
        db, "scout.scanned", connected=sum(1 for s in FREE_SOURCES if router.provider(s.slug))
    )
    db.commit()
    return status(db, router)


def status(db: Session, router: ModelRouter) -> list[dict[str, Any]]:
    since = datetime.now(UTC) - timedelta(days=1)
    ok_calls = func.sum(case((ModelUsage.success, 1), else_=0))
    usage = {
        provider: (int(calls), int(ok or 0))
        for provider, calls, ok in db.execute(
            select(ModelUsage.provider, func.count(), ok_calls)
            .where(ModelUsage.created_at >= since).group_by(ModelUsage.provider)
        ).all()
    }  # fmt: skip
    rows = {r.slug: r for r in db.scalars(select(ModelSource)).all()}
    out = []
    for source in FREE_SOURCES:
        row, provider = rows.get(source.slug), router.provider(source.slug)
        calls, ok = usage.get(source.slug, (0, 0))
        out.append({
            "slug": source.slug, "name": source.name, "env_var": source.env_var,
            "signup_url": source.signup_url, "free_limits": source.free_limits,
            "note": source.note, "recommended": source.recommend,
            "connected": provider is not None,
            "model": provider.spec.model if provider else None,
            "status": row.status if row else ("not_checked" if provider else "not_connected"),
            "free_models": row.free_models if row else 0,
            "error": row.error if row else None,
            "checked_at": row.checked_at if row else None,
            "calls_24h": calls, "failures_24h": calls - ok,
        })  # fmt: skip
    return out
