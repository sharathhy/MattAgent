"""Self-diagnosis: why MATT's bots are (or aren't) working, in plain English, without logs.

Checks the worker heartbeat, whether any free AI model answers, what each recent skill bot
did or why it failed, and what is waiting on the owner. Each problem comes with the fix.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.domain import TaskStatus
from app.llm.providers import ProviderError
from app.llm.router import ModelRouter
from app.models import Experiment, ModelUsage, Task
from app.services import autopilot

STALE = timedelta(minutes=5)


def _aware(value: datetime | None) -> datetime | None:
    return value.replace(tzinfo=UTC) if value is not None and value.tzinfo is None else value


def report(db: Session, router: ModelRouter) -> dict[str, Any]:
    now = datetime.now(UTC)
    settings = router.settings
    pilot = autopilot.get(db)
    beat = _aware(pilot.last_tick_at)
    hour, day = now - timedelta(hours=1), now - timedelta(days=1)

    models = []
    for provider in router.lanes():
        rows = db.scalars(
            select(ModelUsage)
            .where(ModelUsage.provider == provider, ModelUsage.created_at >= day)
            .order_by(ModelUsage.id.desc())
        ).all()
        ok = [r for r in rows if r.success]
        failed = [r for r in rows if not r.success]
        last_ok = _aware(ok[0].created_at) if ok else None
        models.append(
            {
                "provider": provider,
                "calls_24h": len(rows),
                "failures_24h": len(failed),
                "last_success_at": last_ok,
                "last_error": failed[0].error
                if failed and (not ok or failed[0].id > ok[0].id)
                else None,
            }
        )

    bots = db.scalars(
        select(Task)
        .where(Task.objective.startswith(autopilot.BOT_PREFIX))
        .order_by(Task.id.desc())
        .limit(12)
    ).all()
    bot_rows = [
        {
            "task_id": t.id,
            "agent": t.objective.removeprefix(autopilot.BOT_PREFIX),
            "provider": (t.input or {}).get("params", {}).get("provider"),
            "status": t.status,
            "attempts": t.attempts,
            "result": t.output,
            "error": t.error,
            "created_at": t.created_at,
        }
        for t in bots
    ]

    def count(*where: Any) -> int:
        return int(db.scalar(select(func.count()).select_from(Task).where(*where)) or 0)

    queued = count(Task.status == TaskStatus.QUEUED)
    oldest = db.scalar(select(func.min(Task.created_at)).where(Task.status == TaskStatus.QUEUED))
    ready = db.scalars(
        select(Experiment)
        .where(Experiment.status == "completed", Experiment.result.is_not(None))
        .order_by(Experiment.id.desc())
        .limit(5)
    ).all()

    problems: list[dict[str, str]] = []

    def problem(level: str, text: str, fix: str) -> None:
        problems.append({"level": level, "text": text, "fix": fix})

    if not settings.worker_enabled:
        problem(
            "error",
            "The background worker is switched off, so no bot or task ever runs.",
            "Set MATT_WORKER_ENABLED=true in Render.",
        )
    elif beat is None or now - beat > STALE:
        problem(
            "error",
            "The background worker hasn't checked in "
            + (
                "yet."
                if beat is None
                else f"for {int((now - beat) / timedelta(minutes=1))} minutes."
            ),
            "On Render's free plan the server sleeps after 15 minutes with no visitors, and the "
            "bots sleep with it. Add a free UptimeRobot monitor that opens /api/health every 5 "
            "minutes to keep it awake.",
        )
    if not router.lanes():
        problem(
            "error",
            "No free AI model is connected, so the bots cannot think.",
            "Add MATT_GEMINI_API_KEY (free: aistudio.google.com/apikey) in Render.",
        )
    for m in models:
        if m["calls_24h"] and m["last_error"]:
            problem(
                "error" if m["failures_24h"] == m["calls_24h"] else "warn",
                f"{m['provider']}: {m['failures_24h']} of {m['calls_24h']} calls failed in "
                f"24 hours. Latest error: {str(m['last_error'])[:300]}",
                "A 429 means the free daily limit is used up and resets by itself; adding "
                "another free key (Groq, OpenRouter, Cerebras) lets bots switch. A 401 or 403 "
                "means the key is wrong. A 404 means the model name is retired.",
            )
    if not pilot.enabled:
        problem(
            "warn",
            "Autopilot is off, so the bots only work when you ask.",
            'Switch on Autopilot on the home screen or say "start autopilot".',
        )
    recent_bots = [b for b in bot_rows if (_aware(b["created_at"]) or now) >= day]
    failed_bots = [b for b in recent_bots if b["status"] == TaskStatus.FAILED]
    if recent_bots and len(failed_bots) == len(recent_bots):
        problem(
            "error",
            f"All {len(recent_bots)} bot turns in the last day failed. Latest: "
            f"{(failed_bots[0]['error'] or 'unknown error')[:300]}",
            "See the AI model row above for the cause.",
        )
    if beat and now - beat <= STALE and router.lanes() and pilot.enabled and not recent_bots:
        problem(
            "warn",
            "No bot has started in the last day.",
            "Wait a few minutes after a deploy; if it stays, share this panel.",
        )
    if ready:
        problem(
            "info",
            f"{len(ready)} bot idea(s) are ready for you to launch. Revenue stays at "
            "₹0 until a real customer pays and you record it.",
            "Open Experiments and follow each one's 'Your next step'.",
        )

    ok_hour = int(
        db.scalar(
            select(func.count())
            .select_from(ModelUsage)
            .where(ModelUsage.success.is_(True), ModelUsage.created_at >= hour)
        )
        or 0
    )
    return {
        "checked_at": now,
        "healthy": not any(p["level"] == "error" for p in problems),
        "problems": problems,
        "worker": {
            "enabled": settings.worker_enabled,
            "last_heartbeat_at": beat,
            "threads": settings.worker_threads,
            "queued": queued,
            "oldest_queued_at": oldest,
            "running": count(Task.status == TaskStatus.RUNNING),
            "failed_24h": count(Task.status == TaskStatus.FAILED, Task.created_at >= day),
        },
        "models": models,
        "ai_answers_last_hour": ok_hour,
        "autopilot_enabled": pilot.enabled,
        "bots": bot_rows,
        "ready_for_you": [
            {"id": x.id, "name": x.name, "agent_slug": x.agent_slug, "next_step": x.result}
            for x in ready
        ],
    }


def test_models(router: ModelRouter) -> list[dict[str, Any]]:
    """Ask every connected free model for a one-word reply, right now."""
    out = []
    for slug in router.lanes():
        provider = router.provider(slug)
        if provider is None:
            continue
        try:
            done = provider.complete("Reply with the single word OK.", "Are you there?", 16)
            out.append(
                {
                    "provider": slug,
                    "model": provider.spec.model,
                    "ok": True,
                    "reply": done.text.strip()[:40],
                    "latency_ms": done.latency_ms,
                }
            )
        except ProviderError as exc:
            out.append(
                {
                    "provider": slug,
                    "model": provider.spec.model,
                    "ok": False,
                    "error": str(exc)[:400],
                }
            )
    return out
