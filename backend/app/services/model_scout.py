"""Free Model Scout: keeps MATT on the best free AI models it is allowed to use.

Run by the Cost Optimization meta-skill on a schedule. For every curated free-tier service it
checks whether a key is connected, reads that service's model list, picks the best free model
and switches the router to it. It records health and the last 24 hours of calls. It cannot
sign up for accounts or create keys, so it suggests the most useful missing service in Settings
(not in Approvals, which are only for money). It never pays for anything.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.llm.free_sources import FREE_SOURCES
from app.llm.providers import DiscoveringProvider, ProviderError
from app.llm.router import ModelRouter
from app.models import ModelSource, ModelUsage
from app.services import events

AGENT = "meta-cost-optimization"
EVERY = timedelta(hours=6)


def _row(db: Session, slug: str) -> ModelSource:
    row = db.scalar(select(ModelSource).where(ModelSource.slug == slug))
    if row is None:
        row = ModelSource(slug=slug, status="not_connected", free_models=0)
        db.add(row)
    return row


def scan(db: Session, router: ModelRouter) -> list[dict[str, Any]]:
    """Check every free source and switch each connected one to its best free model."""
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
    suggest = next(
        (s.slug for s in FREE_SOURCES if s.recommend and router.provider(s.slug) is None), None
    )
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
            "suggested": source.slug == suggest,
        })  # fmt: skip
    return out
