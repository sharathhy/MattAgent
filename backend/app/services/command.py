"""The command line into MATT (typed or spoken).

Clear requests map to deterministic workflows that run without an AI model. Everything else
goes to MATT's conversational brain (app/services/chat.py), which answers any question and can
queue work for the team.
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
STATUS = re.compile(r"\b(status|what'?s (?:happening|going on)|update me|brief me|report)\b", re.I)
WAKE_PREFIX = re.compile(r"^\W*(?:(?:hey|hi|hello|ok|okay)\W+)?matt\b\W*", re.I)
WAKE_REPLY = "I'm listening. What needs to be done?"
#: "Stop trading" is the owner's spoken kill switch for the trading bots.
TRADING_STOP = re.compile(
    r"\b(?:stop|halt|kill|pause|freeze)\b.{0,20}\b(?:trading|trades)\b|\bkill switch\b", re.I
)
TRADING_STATUS = re.compile(
    r"\b(?:trading|trades|p\s*&\s*l|pnl|demat|portfolio)\b.{0,30}\b(?:status|doing|update|today)\b"
    r"|\bhow(?:'s| is| are)\b.{0,20}\b(?:trading|trades)\b",
    re.I,
)


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

    if TRADING_STOP.search(text):
        from app.trading import service as trading

        acct = trading.kill(db, user, router)
        return CommandResult(
            "Trading stopped. The kill switch is on, every open position was squared off, and no "
            f"bot will open a trade until you press Resume on the Trading page ({acct.mode} mode).",
            "trading_stop",
        )

    if TRADING_STATUS.search(text) and len(text) < 100:
        from app.trading import service as trading

        return CommandResult(trading.spoken_status(db), "trading_status")

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
            "My AI brain is switched off because no free AI model is connected, so I can only do "
            "the built-in commands. Add a free Gemini key as MATT_GEMINI_API_KEY in Render "
            "(Settings, Free Model Scout lists more free options). Until then I can find "
            'businesses ("find gyms in Bangalore"), audit a website and give you a status report.',
            "no_model",
        )

    # Everything else: MATT's conversational brain answers and acts through its tools.
    from app.services import chat

    said = chat.respond(db, router, user, text)
    return CommandResult(said.reply, said.intent, said.task_id, said.data)
