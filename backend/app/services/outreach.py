"""The sales agent's own outreach: it emails each offer and one follow-up by itself.

Runs from the background worker. Each pass sends at most one email, so a day's handful is spread
out like a person writing them, and never more than ``MATT_AUTO_SEND_DAILY_CAP`` in 24 hours.
Only businesses that publish an email address are written to, once, with one follow-up three days
later if they have not moved on. Every email has a one-click unsubscribe link; an unsubscribed
address is never written to again. WhatsApp cannot be sent automatically, so those offers stay on
the Sales Desk for the owner. No money moves here: the offer only asks the customer to pay the
owner's own UPI ID.
"""

import hashlib
import hmac
import logging
import os
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.domain import LeadStatus
from app.db.base import utcnow
from app.llm.router import ModelRouter
from app.models import Business, Event, Knowledge, Lead, User
from app.services import demo_sites, events, mailer, payments, sales
from app.services.errors import ServiceError

log = logging.getLogger(__name__)

EVERY = timedelta(minutes=15)
FOLLOW_UP_AFTER = timedelta(days=3)
BACK_OFF = timedelta(hours=2)  # after a failed send, so a broken setup doesn't burn leads
SENT = "sales.offer_emailed"
FAILED = "sales.email_failed"
SUPPRESSED = "suppressed"
#: Outreach states a business can be emailed from for the first time.
FIRST_FROM = (None, "ready", "needs_fix")
#: Automatic sending stays off until the owner explicitly approves it.
SWITCHED_ON = False
_PLACEHOLDER = re.compile(r"\[[^\]\n]{2,40}\]")


def base_url(settings: Settings) -> str | None:
    url = settings.public_url or os.environ.get("RENDER_EXTERNAL_URL") or ""
    return url.rstrip("/") or None


def _sig(settings: Settings, lead_id: int) -> str:
    key = settings.secret_key.encode()
    return hmac.new(key, f"unsubscribe:{lead_id}".encode(), hashlib.sha256).hexdigest()[:24]


def unsubscribe_url(settings: Settings, base: str, lead: Lead) -> str:
    return f"{base}/u/{lead.id}/{_sig(settings, lead.id)}"


def _email(value: str | None) -> str:
    return (value or "").strip().lower()


def suppressed(db: Session, email: str) -> bool:
    return (
        db.scalar(
            select(Knowledge.id).where(
                Knowledge.kind == SUPPRESSED, Knowledge.title == _email(email)
            )
        )
        is not None
    )


def _since(db: Session, kind: str, after: datetime) -> list[Event]:
    return list(db.scalars(select(Event).where(Event.type == kind, Event.created_at >= after)))


def sent_last_day(db: Session) -> int:
    after = utcnow() - timedelta(days=1)
    stmt = select(func.count()).select_from(Event).where(Event.type == SENT,
                                                         Event.created_at >= after)  # fmt: skip
    return int(db.scalar(stmt) or 0)


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def status(db: Session, settings: Settings) -> dict[str, Any]:
    """What the Sales Desk shows about automatic sending, with the setup steps still missing."""
    way, base = mailer.channel(settings), base_url(settings)
    missing = []
    if not SWITCHED_ON:
        missing.append("Waiting for the owner's go-ahead to let the sales agent email by itself.")
    if way is None:
        missing.append(
            "Connect an email to send from: on Render's free plan create a free Brevo account, "
            "verify your Gmail address there as a sender, then add MATT_BREVO_API_KEY and "
            "MATT_MAIL_FROM (that address) in Render, Environment. On a host that allows SMTP, "
            "MATT_SMTP_HOST=smtp.gmail.com, MATT_SMTP_USERNAME and MATT_SMTP_PASSWORD (a Google "
            "app password) work instead."
        )
    if base is None:
        missing.append("Set MATT_PUBLIC_URL to this site's address so sample links work.")
    if settings.auto_send_daily_cap == 0:
        missing.append("MATT_AUTO_SEND_DAILY_CAP is 0, which switches automatic sending off.")
    if not settings.worker_enabled:
        missing.append("The background worker is off (MATT_WORKER_ENABLED).")
    failures = _since(db, FAILED, utcnow() - timedelta(days=1))
    return {
        "enabled": not missing,
        "channel": way,
        "sender": mailer.sender(settings),
        "daily_cap": settings.auto_send_daily_cap,
        "sent_last_24h": sent_last_day(db),
        "last_error": str(failures[-1].payload.get("error")) if failures else None,
        "missing": missing,
    }


def _owner(db: Session) -> User | None:
    return db.scalar(select(User).where(User.role == "owner").order_by(User.id))


def _first_candidate(db: Session, skip: set[int]) -> Lead | None:
    leads = db.scalars(
        select(Lead)
        .join(Business)
        .where(
            Lead.status.in_([LeadStatus.NEW, LeadStatus.QUALIFIED]),
            Business.public_email.is_not(None),
            Business.public_email != "",
            (Business.outreach_status.is_(None))
            | Business.outreach_status.in_([s for s in FIRST_FROM if s]),
        )
        .order_by(Business.opportunity_score.desc().nulls_last(), Lead.id)
        .limit(50)
    ).all()
    return next((x for x in leads if x.id not in skip and "@" in (x.business.public_email or "")
                 and not suppressed(db, x.business.public_email or "")), None)  # fmt: skip


def _follow_up_candidate(db: Session, skip: set[int]) -> Lead | None:
    now = utcnow()
    firsts = [e for e in _since(db, SENT, now - timedelta(days=14))
              if e.payload.get("kind") == "offer"]  # fmt: skip
    for ev in firsts:
        if now - _aware(ev.created_at) < FOLLOW_UP_AFTER:
            continue
        lead = db.get(Lead, int(ev.payload.get("lead_id") or 0))
        if (lead is None or lead.id in skip or lead.status != LeadStatus.CONTACTED
                or lead.business.outreach_status != "emailed"
                or suppressed(db, lead.business.public_email or "")):  # fmt: skip
            continue
        return lead
    return None


def _ensure_sample(db: Session, router: ModelRouter, settings: Settings, lead: Lead) -> None:
    if demo_sites.samples(db, lead):
        return
    try:
        demo_sites.build(db, router, lead, settings.upi_payee_name)
    except ServiceError:
        log.warning("could not build a demo site for lead %s", lead.id)


def _ensure_price(db: Session, settings: Settings, lead: Lead) -> None:
    if sales._request(db, lead) is not None or payments.upi_id(db, settings) is None:
        return
    owner = _owner(db)
    if owner is None:
        return
    try:
        sales.price(db, settings, owner, lead.id, sales.list_price(lead))
    except ServiceError:
        log.warning("could not price the offer for lead %s", lead.id)


def _footer(settings: Settings, unsubscribe: str, business: str) -> str:
    return (
        f"\n\n--\n{settings.upi_payee_name}\n"
        f"You are getting this one-off note because {business} lists this email address "
        f"publicly. To never hear from me again, open: {unsubscribe}"
    )


def _offer_text(db: Session, settings: Settings, lead: Lead, base: str) -> tuple[str, str]:
    draft = lead.outreach_draft if lead.business.outreach_status == "ready" else None
    if draft:
        draft = draft.replace("[Your name]", settings.upi_payee_name)
        if _PLACEHOLDER.search(draft):
            draft = None  # an unfilled placeholder would look careless; use the plain offer
    text = sales.message(db, settings, lead, base, text=draft or None)
    if not draft:
        text = text.replace("[Your name]", settings.upi_payee_name)
    subject, body = sales.split_subject(lead, text)
    # The unsubscribe link replaces "reply STOP": replies reach the owner, not MATT.
    body = "\n".join(ln for ln in body.splitlines() if "STOP" not in ln).strip()
    return subject, body


def _follow_up_text(db: Session, lead: Lead, base: str) -> tuple[str, str]:
    b = lead.business
    links = sales.sample_links(db, lead, base)
    lines = [
        f"Hello {b.name} team,",
        "",
        f"Just checking you saw my note from a few days ago about {lead.service.lower()}.",
    ]
    if links:
        lines.append(f"The free sample I made for you is still here: {links[0]['url']}")
    lines += ["", "If it's not for you, no problem at all; this is the last time I'll write."]
    return f"Re: {sales.split_subject(lead, lead.outreach_draft or '')[0]}", "\n".join(lines)


def _send(db: Session, settings: Settings, lead: Lead, base: str, kind: str) -> bool:
    if kind == "offer":
        subject, body = _offer_text(db, settings, lead, base)
    else:
        subject, body = _follow_up_text(db, lead, base)
    b = lead.business
    unsubscribe = unsubscribe_url(settings, base, lead)
    mail = mailer.Mail(to=_email(b.public_email), subject=subject[:200],
                       body=body + _footer(settings, unsubscribe, b.name),
                       unsubscribe_url=unsubscribe)  # fmt: skip
    try:
        way = mailer.send(settings, mail)
    except mailer.MailError as exc:
        events.emit(db, FAILED, lead_id=lead.id, error=str(exc)[:400])
        db.commit()
        log.warning("offer email to lead %s failed: %s", lead.id, exc)
        return False
    lead.status = LeadStatus.CONTACTED
    if kind == "offer":
        b.outreach_status = "emailed"
        lead.next_action = (
            "The sales agent emailed the offer. Replies arrive in your inbox; one follow-up goes "
            "out in 3 days if nothing changes. Mark it Paid when the money arrives."
        )
    else:
        b.outreach_status = "followed_up"
        lead.next_action = "Offer and one follow-up emailed. No more emails will be sent."
    events.emit(db, SENT, lead_id=lead.id, kind=kind, via=way)
    db.commit()
    return True


def run(db: Session, router: ModelRouter) -> str | None:
    """One pass: send a single due follow-up or new offer. Returns what was done, if anything."""
    settings = router.settings
    if not status(db, settings)["enabled"] or sent_last_day(db) >= settings.auto_send_daily_cap:
        return None
    now = utcnow()
    failures = _since(db, FAILED, now - timedelta(days=1))
    if failures and now - _aware(failures[-1].created_at) < BACK_OFF:
        return None
    skip = {int(e.payload.get("lead_id") or 0) for e in failures}
    base = base_url(settings) or ""
    lead = _follow_up_candidate(db, skip)
    kind = "follow_up"
    if lead is None:
        lead, kind = _first_candidate(db, skip), "offer"
    if lead is None:
        return None
    if kind == "offer":
        _ensure_sample(db, router, settings, lead)
        _ensure_price(db, settings, lead)
    if not _send(db, settings, lead, base, kind):
        return None
    return f"Emailed {'a follow-up' if kind == 'follow_up' else 'an offer'} to {lead.business.name}"


def opt_out(db: Session, settings: Settings, lead_id: int, sig: str) -> bool:
    """Honour an unsubscribe link: stop all contact with this business and its address."""
    if not hmac.compare_digest(sig, _sig(settings, lead_id)):
        return False
    lead = db.get(Lead, lead_id)
    if lead is None:
        return False
    b, email = lead.business, _email(lead.business.public_email)
    if email and not suppressed(db, email):
        db.add(Knowledge(kind=SUPPRESSED, title=email[:300], content="Unsubscribed from offers.",
                         tags=["unsubscribe"], source=f"lead:{lead.id}:unsubscribe"))  # fmt: skip
    b.outreach_status = "opted_out"
    if lead.status != LeadStatus.WON:
        lead.status = LeadStatus.LOST
    lead.next_action = "Unsubscribed. Never contact this business again."
    events.emit(db, "sales.unsubscribed", lead_id=lead.id)
    db.commit()
    return True
