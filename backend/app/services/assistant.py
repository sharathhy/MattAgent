"""Everyday spoken requests answered directly from MATT's records, Alexa-style.

These need no AI model: earnings, recording a sale, approvals, leads, opportunities, memory,
opening a page, the time. Anything not recognised here falls through to the agents.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import money
from app.core.domain import ApprovalStatus, RevenueCategory
from app.models import Approval, Knowledge, Lead, Opportunity, User
from app.services import autopilot, changes, earnings, events


@dataclass
class Answer:
    reply: str
    intent: str
    data: dict[str, Any] = field(default_factory=dict)


PAGES = {
    "command center": "/command-center", "home": "/command-center", "dashboard": "/command-center",
    "workforce": "/workforce", "agents": "/agents", "skills": "/agents", "tasks": "/tasks",
    "workflows": "/workflows", "tools": "/tools", "approvals": "/approvals",
    "analytics": "/analytics", "opportunities": "/opportunities", "businesses": "/businesses",
    "leads": "/leads", "customers": "/customers", "products": "/products",
    "revenue": "/revenue", "earnings": "/revenue", "experiments": "/experiments",
    "memory": "/memory", "audit log": "/audit-log", "settings": "/settings",
}  # fmt: skip
STREAM_WORDS = {
    "website": RevenueCategory.WEBSITES, "web site": RevenueCategory.WEBSITES,
    "saas": RevenueCategory.SAAS, "subscription": RevenueCategory.SUBSCRIPTIONS,
    "automation": RevenueCategory.AUTOMATION, "consult": RevenueCategory.AI_CONSULTING,
    "content": RevenueCategory.CONTENT, "video": RevenueCategory.CONTENT,
    "clip": RevenueCategory.CONTENT, "affiliate": RevenueCategory.AFFILIATE,
    "lead": RevenueCategory.LEAD_GENERATION, "product": RevenueCategory.DIGITAL_PRODUCTS,
}  # fmt: skip

CODE_CHANGE = re.compile(
    r"^(?:please\s+)?(?:change|modify|update|edit|fix|improve|add)\b.*\b(?:your|matt'?s?)\s+"
    r"(?:\w+\s+){0,2}?(?:code|codebase|app|ui|website|screen|page|interface)\b"
)
NAVIGATE = re.compile(r"^(?:open|show|go to|take me to)\s+(?:the\s+|my\s+)?([a-z ]+?)(?:\s+page)?$")
RECORD = re.compile(
    r"\b(record|add|log|note|i (?:got|received|earned|made|spent|paid))\b.*?"
    r"(?:rs\.?|inr|₹|rupees)?\s*(\d[\d,]*(?:\.\d+)?)\s*(k|thousand|lakh|lakhs|lac|crore)?",
)
MONEY = re.compile(
    r"₹|\b(revenue|payment|paid|pay|income|sale|sold|received|earned|expense|spent|rupees|rs|"
    r"inr|invoice|lakh|lakhs|crore)\b"
)
QUESTION = re.compile(
    r"\b(how much|what(?:'s| is| are| did)?|today|this (?:week|month)|total|show|tell)\b"
)
EXPENSE = re.compile(r"\b(expense|spent|paid|cost|bill)\b")
EARNINGS = re.compile(r"\b(earn(?:ed|ing|ings)?|revenue|income|sales|money|made|profit)\b")
EARNERS = re.compile(r"\b(which|what|who)\b.*\b(skills?|agents?)\b.*\bearn")
APPROVALS = re.compile(r"\b(approvals?|pending|waiting for me|need my (?:ok|approval))\b")
LEADS = re.compile(r"\b(top|best|show|list|my)\b.*\bleads?\b|^leads?$")
OPPS = re.compile(r"\b(top|best|show|list|my)\b.*\bopportunit(?:y|ies)\b")
REMEMBER = re.compile(r"^(?:please\s+)?remember(?:\s+that)?\s+(.{3,})$", re.I | re.S)
TIME = re.compile(r"\bwhat(?:'s| is)? the (time|date|day)\b|\bwhat time is it\b")
THANKS = re.compile(r"^(thanks|thank you|great|awesome|ok(?:ay)?|cool|nice)[.! ]*$")
DISMISS = re.compile(r"^(stop|cancel|never ?mind|go to sleep|that'?s all|nothing)[.! ]*$")
AUTOPILOT_ON = re.compile(
    r"\b(start|turn on|enable|resume)\b.*\b(autopilot|auto ?pilot|working on your own|autonomous)\b"
    r"|^(start working|get to work|work on your own)$"
)
AUTOPILOT_OFF = re.compile(
    r"\b(stop|turn off|disable|pause)\b.*\b(autopilot|auto ?pilot|working on your own|autonomous)\b"
    r"|^(stop working|pause work)$"
)
AUTOPILOT_STATUS = re.compile(r"\bwhat are you (working on|doing)\b|\bautopilot( status)?\b")
HELP = re.compile(r"\b(what can you do|help|how do (?:i|you) use)\b")

MULTIPLIER = {"k": 1_000, "thousand": 1_000, "lakh": 100_000, "lakhs": 100_000,
              "lac": 100_000, "crore": 10_000_000}  # fmt: skip


def rupees(value: float | Decimal) -> str:
    v = float(value)
    return f"₹{v:,.0f}" if v == int(v) else f"₹{v:,.2f}"


def _amount(number: str, unit: str | None) -> Decimal | None:
    try:
        value = Decimal(number.replace(",", ""))
    except InvalidOperation:
        return None
    return value * MULTIPLIER.get(unit or "", 1)


def _stream(text: str) -> str:
    for word, category in STREAM_WORDS.items():
        if word in text:
            return category
    return RevenueCategory.OTHER


def _earnings_reply(db: Session, tz: str, text: str) -> Answer:
    e = earnings.summary(db, tz, days=7)
    if "week" in text:
        reply = f"You've earned {rupees(e['week_inr'])} in the last 7 days."
    elif "month" in text:
        reply = f"You've earned {rupees(e['month_inr'])} this month."
    elif "total" in text or "all time" in text or "so far" in text:
        reply = f"Total recorded revenue is {rupees(e['total_inr'])}."
    else:
        reply = (
            f"Today you've earned {rupees(e['today_inr'])}. This month: {rupees(e['month_inr'])}."
        )
    if e["total_inr"] == 0:
        reply += " No revenue has been recorded yet. Tell me when you get paid and I'll log it."
    return Answer(reply, "earnings", {"earnings": e, "navigate": "/revenue"})


def answer(db: Session, user: User, raw: str, tz: str) -> Answer | None:
    text = raw.lower().strip().rstrip("?.!")

    if money.is_outbound(text):
        return Answer(money.REFUSAL, "money_rule")
    if CODE_CHANGE.search(text):
        if user.role != "owner":
            return Answer("Only the owner can ask me to change my own code.", "code_change")
        change = changes.create(db, user, raw.strip())
        return Answer(
            "I'll draft that change and show you the plan and the exact code in Approvals. "
            "Nothing changes until you approve; then I open a pull request for you to merge.",
            "code_change",
            {"change_id": change.id, "navigate": "/settings"},
        )
    if THANKS.match(text):
        return Answer("You're welcome.", "thanks")
    if DISMISS.match(text):
        return Answer('Okay. Say "Hey Matt" when you need me.', "dismiss")
    if HELP.search(text):
        return Answer(
            'I can find businesses and rank leads ("find dentists in Mysore"), audit a '
            "website, tell you today's earnings, log a payment (\"record 15,000 from a website "
            'project"), read your approvals and top leads, remember things, open any page, and '
            "pass bigger questions to the CEO agent.",
            "help",
        )
    if AUTOPILOT_ON.search(text) or AUTOPILOT_OFF.search(text):
        on = bool(AUTOPILOT_ON.search(text))
        if user.role != "owner":
            return Answer("Only the owner can switch autopilot on or off.", "autopilot")
        autopilot.update(db, user, {"enabled": on})
        return Answer(
            "Autopilot is on. I'll keep finding and auditing leads, scoring opportunities and "
            "drafting pitches for your approval. I won't send or spend anything without you."
            if on
            else "Autopilot is off. I'll only work when you ask.",
            "autopilot",
            {"enabled": on},
        )
    if AUTOPILOT_STATUS.search(text):
        row = autopilot.get(db)
        if not row.enabled:
            return Answer("Autopilot is off. Say \"start autopilot\" to let me work on my own.",
                          "autopilot", {"enabled": False})  # fmt: skip
        last = row.last_action or "getting started"
        return Answer(f"Autopilot is on. Latest: {last}.", "autopilot", {"enabled": True})

    if TIME.search(text):
        now = datetime.now(ZoneInfo(tz))
        return Answer(f"It's {now:%-I:%M %p} on {now:%A, %-d %B}.", "time")

    if (
        MONEY.search(text)
        and (m := RECORD.search(text))
        and (amount := _amount(m.group(2), m.group(3)))
    ):
        kind = "expense" if EXPENSE.search(text) else "revenue"
        category = _stream(text)
        entry = earnings.record(
            db, user, kind=kind, amount_inr=amount, category=category,
            description=raw.strip()[:500], occurred_on=earnings.today(tz),
        )  # fmt: skip
        label = category.replace("_", " ")
        return Answer(
            f"Recorded {rupees(amount)} {kind} for today under {label}.",
            "record_ledger",
            {"ledger_id": entry.id, "navigate": "/revenue"},
        )

    if EARNERS.search(text):
        agents = earnings.summary(db, tz, days=1)["earning_agents"]
        if not agents:
            return Answer(
                "No skill has recorded revenue yet. When you log a payment, say which agent "
                "earned it on the Revenue page and I'll track it.",
                "earning_skills",
            )
        top = ", ".join(f"{a['name']} {rupees(a['total_inr'])}" for a in agents[:3])
        return Answer(f"Skills with recorded revenue: {top}.", "earning_skills",
                      {"earning_agents": agents})  # fmt: skip

    if EARNINGS.search(text) and QUESTION.search(text) and len(text) < 90:
        return _earnings_reply(db, tz, text)

    if APPROVALS.search(text) and len(text) < 80:
        pending = db.scalars(
            select(Approval).where(Approval.status == ApprovalStatus.PENDING).order_by(Approval.id)
        ).all()
        if not pending:
            return Answer("Nothing is waiting for your approval.", "approvals")
        first = "; ".join(a.action for a in pending[:3])
        return Answer(f"{len(pending)} waiting for you: {first}.", "approvals",
                      {"navigate": "/approvals"})  # fmt: skip

    if LEADS.search(text) and len(text) < 60:
        leads = db.scalars(select(Lead).order_by(Lead.id.desc()).limit(50)).all()
        ranked = sorted(leads, key=lambda lead: lead.business.opportunity_score or 0, reverse=True)
        if not ranked:
            return Answer('No leads yet. Try "find gyms in Mysore".', "leads")
        top = ", ".join(f"{lead.business.name} ({lead.service.lower()})" for lead in ranked[:3])
        return Answer(f"Your top leads: {top}.", "leads", {"navigate": "/leads"})

    if OPPS.search(text) and len(text) < 60:
        opps = db.scalars(select(Opportunity).order_by(Opportunity.score.desc()).limit(3)).all()
        if not opps:
            return Answer("No opportunities scored yet.", "opportunities")
        top = ", ".join(f"{o.title} ({o.score:.0f})" for o in opps)
        return Answer(f"Top opportunities: {top}. Scores are estimates.", "opportunities",
                      {"navigate": "/opportunities"})  # fmt: skip

    if m := REMEMBER.match(raw.strip()):
        content = m.group(1).strip()
        note = Knowledge(kind="long_term", title=content[:80], content=content,
                         tags=["voice"], source=f"user:{user.id}")  # fmt: skip
        db.add(note)
        events.emit(db, "memory.saved", title=note.title)
        db.commit()
        return Answer("Got it, I'll remember that.", "remember", {"knowledge_id": note.id})

    if (m := NAVIGATE.match(text)) and (path := PAGES.get(m.group(1).strip())):
        return Answer(f"Opening {m.group(1).strip()}.", "navigate", {"navigate": path})
    return None
