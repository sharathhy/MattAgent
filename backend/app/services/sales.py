"""Sales desk: the one path from a found business to a real payment.

MATT finds local businesses with weak websites, audits them and writes a personal offer. The
desk puts each offer next to the business's public contact with ready WhatsApp and email
links and a UPI payment request in the owner's name. The owner sends it from their own phone
or email (MATT sends nothing), marks it sent, and confirms the payment when it arrives, which
records the revenue. Money only ever comes in.
"""

import re
from decimal import Decimal
from typing import Any
from urllib.parse import quote

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.domain import LeadStatus, RevenueCategory
from app.models import Business, Lead, PaymentRequest, User
from app.services import events, payments
from app.services.errors import NotFoundError, ServiceError

DEFAULT_PRICE = Decimal("4999")
_TAG = "(lead #{id})"


def _tag(lead: Lead) -> str:
    return _TAG.format(id=lead.id)


def template_offer(lead: Lead) -> str:
    """A plain, honest offer from the audit alone, for when no AI draft exists yet."""
    b = lead.business
    findings = [str(f) for f in (b.audit or {}).get("findings", [])[:3]]
    site = b.website or "your website"
    lines = [f"Hello {b.name} team,", ""]
    if b.website:
        lines.append(f"I looked at {site} and noticed a few things that may cost you customers:")
        lines += [f"- {f}" for f in findings] or ["- it is hard to use on a phone"]
    else:
        lines.append("I couldn't find a website for your business, so people searching online "
                     "may not find you.")  # fmt: skip
    lines += [
        "",
        f"I can fix this for you ({lead.service.lower()}). You see the plan first and pay only "
        "if you want to go ahead.",
        "",
        "Reply STOP and I won't contact you again.",
        "[Your name]",
    ]
    return "\n".join(lines)


def _phone(raw: str | None) -> str | None:
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 10:
        digits = "91" + digits  # Indian mobile without country code
    if digits.startswith("0") and len(digits) == 11:
        digits = "91" + digits[1:]
    return digits if 11 <= len(digits) <= 15 else None


def _request(db: Session, lead: Lead) -> PaymentRequest | None:
    return db.scalar(
        select(PaymentRequest)
        .where(PaymentRequest.purpose.endswith(_tag(lead)), PaymentRequest.status != "cancelled")
        .order_by(PaymentRequest.id.desc())
    )


def message(db: Session, settings: Settings, lead: Lead) -> str:
    text = (lead.outreach_draft or template_offer(lead)).strip()
    pay = _request(db, lead)
    if pay is not None and pay.upi_id:
        text += (
            f"\n\nIf you'd like to go ahead, the price is ₹{pay.amount_inr:,.0f}, paid by UPI to "
            f"{pay.upi_id} (reference {pay.reference})."
        )
    return text


def card(db: Session, settings: Settings, lead: Lead) -> dict[str, Any]:
    b = lead.business
    text = message(db, settings, lead)
    subject = next((ln[8:].strip() for ln in text.splitlines() if ln.startswith("Subject:")),
                   f"A quick fix for {b.name}'s website")  # fmt: skip
    body = "\n".join(ln for ln in text.splitlines() if not ln.startswith("Subject:")).strip()
    phone = _phone(b.public_phone)
    pay = _request(db, lead)
    amount = pay.amount_inr if pay else lead.estimated_value_min_inr or DEFAULT_PRICE
    return {
        "lead_id": lead.id, "business": b.name, "category": b.category, "city": b.city,
        "website": b.website, "website_score": b.website_score,
        "opportunity_score": b.opportunity_score,
        "findings": (b.audit or {}).get("findings", [])[:3],
        "public_phone": b.public_phone, "public_email": b.public_email,
        "status": lead.status, "drafted_by_ai": bool(lead.outreach_draft),
        "price_inr": float(amount),
        "message": body, "subject": subject,
        "whatsapp_url": f"https://wa.me/{phone}?text={quote(body)}" if phone else None,
        "email_url": (f"mailto:{b.public_email}?subject={quote(subject)}&body={quote(body)}"
                      if b.public_email else None),
        "payment": payments.out(db, pay, settings) if pay else None,
    }  # fmt: skip


def desk(db: Session, settings: Settings) -> dict[str, Any]:
    leads = db.scalars(
        select(Lead)
        .join(Business)
        .where(Lead.status.not_in([LeadStatus.LOST, LeadStatus.WON]))
        .order_by(Business.opportunity_score.desc().nulls_last(), Lead.id.desc())
        .limit(30)
    ).all()
    reachable = [lead for lead in leads if lead.business.public_phone or lead.business.public_email]
    return {
        "upi_ready": payments.upi_id(db, settings) is not None,
        "offers": [card(db, settings, lead) for lead in reachable],
        "without_contact": len(leads) - len(reachable),
    }


def _lead(db: Session, lead_id: int) -> Lead:
    lead = db.get(Lead, lead_id)
    if lead is None:
        raise NotFoundError("Lead not found")
    return lead


def price(db: Session, settings: Settings, user: User, lead_id: int, amount: Decimal) -> Lead:
    """Attach (or replace) the UPI payment request the offer asks the customer to pay."""
    lead = _lead(db, lead_id)
    old = _request(db, lead)
    if old is not None:
        if old.status == "received":
            raise ServiceError("This customer has already paid")
        payments.cancel(db, user, old.id)
    payments.create(db, settings, user, amount_inr=amount,
                    purpose=f"{lead.service} for {lead.business.name} {_tag(lead)}"[-300:],
                    category=RevenueCategory.WEBSITES)  # fmt: skip
    return lead


def mark_sent(db: Session, user: User, lead_id: int) -> Lead:
    lead = _lead(db, lead_id)
    lead.status = LeadStatus.CONTACTED
    lead.business.outreach_status = "sent"
    lead.next_action = "Offer sent by the owner. Follow up once in 3 days if there is no reply."
    events.emit(db, "sales.offer_sent", lead_id=lead.id, by=str(user.id))
    db.commit()
    return lead


def mark_paid(db: Session, user: User, lead_id: int) -> Lead:
    lead = _lead(db, lead_id)
    pay = _request(db, lead)
    if pay is None:
        raise ServiceError("Set a price first so there is a payment to confirm")
    if pay.status != "received":
        payments.mark_received(db, user, pay.id)
    lead.status = LeadStatus.WON
    lead.next_action = "Paid. Deliver the work."
    events.emit(db, "sales.offer_paid", lead_id=lead.id, amount_inr=str(pay.amount_inr))
    db.commit()
    return lead
