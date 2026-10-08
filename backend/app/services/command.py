"""The command line into MATT (typed or spoken).

Clear requests map to deterministic workflows that run without an AI model. Everything else
goes to the CEO agent, which answers and may delegate to its executives.
"""

import re
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.domain import ApprovalStatus, TaskStatus
from app.llm.router import ModelRouter
from app.models import Approval, Lead, Task, User
from app.plugins.business_discovery import CATEGORIES
from app.services import assistant, events, tasks

SYNONYMS = {
    "restaurant": "restaurants", "cafe": "restaurants", "cafes": "restaurants",
    "gym": "gyms", "fitness": "gyms", "dentist": "dentists", "dental": "dentists",
    "salon": "salons", "beauty": "salons", "spa": "salons", "realtor": "real estate",
    "builder": "construction", "builders": "construction", "lawyer": "law firms",
    "lawyers": "law firms", "accountant": "accountants", "ca": "accountants",
    "clinic": "clinics", "doctor": "clinics", "doctors": "clinics", "hotel": "hotels",
    "shop": "retail", "shops": "retail", "store": "retail", "stores": "retail",
    "school": "education", "schools": "education", "garage": "automotive",
    "plumber": "home services", "electrician": "home services",
}  # fmt: skip
WAKE = re.compile(r"^\W*(hey|hi|hello|ok|okay)?\W*(matt|mat|mad)?\W*$", re.I)
FIND = re.compile(
    r"\b(find|discover|search|look for|get)\b.*?\bin\s+([a-z][a-z .'-]{1,40}?)"
    r"(?:\s+(?:that|which|with|who|and|for|needing)\b.*)?\s*[.?!]?$",
    re.I,
)
AUDIT = re.compile(
    r"\b(audit|analy[sz]e|check|score)\b.*?((?:https?://)?[a-z0-9-]+(?:\.[a-z0-9-]+)+\S*)", re.I
)
OPPORTUNITY = re.compile(r"\b(opportunit(?:y|ies)|business ideas?)\b", re.I)
STATUS = re.compile(r"\b(status|what'?s (?:happening|going on)|update me|brief me|report)\b", re.I)
WAKE_PREFIX = re.compile(r"^\W*(?:(?:hey|hi|hello|ok|okay)\W+)?matt\b\W*", re.I)
WAKE_REPLY = "I'm listening. What needs to be done?"


@dataclass
class CommandResult:
    reply: str
    intent: str
    task_id: int | None = None
    data: dict[str, Any] = field(default_factory=dict)


def _category(text: str) -> str | None:
    lower = text.lower()
    for name in sorted(CATEGORIES, key=len, reverse=True):
        if name in lower:
            return name
    for word in re.findall(r"[a-z]+", lower):
        if word in SYNONYMS:
            return SYNONYMS[word]
    return None


def status_report(db: Session) -> str:
    def count(model: Any, *where: Any) -> int:
        return int(db.scalar(select(func.count()).select_from(model).where(*where)) or 0)

    running = count(Task, Task.status.in_([TaskStatus.QUEUED, TaskStatus.RUNNING]))
    pending = count(Approval, Approval.status == ApprovalStatus.PENDING)
    leads = count(Lead)
    failed = count(Task, Task.status == TaskStatus.FAILED)
    return (
        f"{running} task{'s' * (running != 1)} in progress, {pending} waiting for your "
        f"approval, {leads} lead{'s' * (leads != 1)} in the pipeline"
        + (f", and {failed} failed task{'s' * (failed != 1)} to look at." if failed else ".")
    )


def handle(db: Session, router: ModelRouter, user: User, text: str) -> CommandResult:
    text = WAKE_PREFIX.sub("", text.strip()).strip()
    actor = str(user.id)
    events.emit(db, "command.received", text=text[:500], by=actor)
    db.commit()
    if not text or WAKE.match(text):
        return CommandResult(WAKE_REPLY, "wake")

    if quick := assistant.answer(db, user, text, router.settings.timezone):
        return CommandResult(quick.reply, quick.intent, None, quick.data)

    if (m := FIND.search(text)) and (category := _category(text)):
        city = m.group(2).strip().title()
        task = tasks.create(
            db, kind="workflow", created_by=actor,
            objective=f"Find {category} in {city} and rank website opportunities",
            input={"workflow": "website_opportunities",
                   "params": {"city": city, "category": category, "limit": 10}},
        )  # fmt: skip
        return CommandResult(
            f"On it. I'm finding {category} in {city}, auditing their websites and ranking "
            "leads. Results will appear in Leads.", "website_opportunities", task.id,
        )  # fmt: skip

    if m := AUDIT.search(text):
        url = m.group(2).rstrip(".,!?")
        task = tasks.create(
            db, kind="workflow", created_by=actor, objective=f"Audit {url}",
            input={"workflow": "audit_website", "params": {"url": url}},
        )  # fmt: skip
        return CommandResult(f"Auditing {url} now.", "audit_website", task.id)

    if STATUS.search(text) and len(text) < 80:
        return CommandResult(status_report(db), "status")

    if not router.available:
        return CommandResult(
            "I can't reason about that yet because no AI model is connected. Add a free Gemini "
            "key as MATT_GEMINI_API_KEY in Render. Without it I can still find businesses "
            '("find gyms in Bangalore"), audit a website, and give you a status report.',
            "no_model",
        )

    if OPPORTUNITY.search(text):
        task = tasks.create(
            db, kind="workflow", created_by=actor, objective=text,
            input={"workflow": "opportunity_research", "params": {"focus": text}},
        )  # fmt: skip
        return CommandResult(
            "Researching opportunities and scoring them now. They'll appear in Opportunities.",
            "opportunity_research", task.id,
        )  # fmt: skip

    # Open-ended: the CEO answers now, delegating follow-up work to the queue.
    task = tasks.create(db, objective=text, created_by=actor, agent_slug="ceo", priority=1)
    task.status, task.attempts = TaskStatus.RUNNING, 1
    db.commit()
    task = tasks.execute(db, task, router)
    if task.status == TaskStatus.SUCCEEDED:
        delegated = (task.output_data or {}).get("delegated_task_ids", [])
        reply = task.output or "Done."
        if delegated:
            reply += f"\n\nI've assigned {len(delegated)} follow-up task(s) to the team."
        return CommandResult(reply, "ceo", task.id, {"delegated_task_ids": delegated})
    if task.status == TaskStatus.WAITING_APPROVAL:
        return CommandResult(
            "That needs more AI budget than you've allowed. I've put a request in Approvals.",
            "budget", task.id,
        )  # fmt: skip
    return CommandResult(
        f"I couldn't finish that: {task.error or 'unknown error'}. "
        + ("I'll retry shortly." if task.status == TaskStatus.QUEUED else ""),
        "error", task.id,
    )  # fmt: skip
