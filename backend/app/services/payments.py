"""Receive-only payments: ask a customer to pay the owner directly by UPI.

This module deliberately has no function that sends, transfers, withdraws, refunds or debits
money (see app/core/money.py; a test checks it). A payment request is a UPI link and QR code
addressed to the owner's own UPI ID (``MATT_UPI_ID``), so money lands straight in the owner's
account (for example PhonePe). MATT cannot see that account, so a request becomes revenue only
when the owner confirms the money arrived.
"""

import re
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from urllib.parse import quote, urlencode

import segno
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import money
from app.core.config import Settings
from app.core.domain import RevenueCategory
from app.models import Customer, PaymentRequest, User
from app.services import accounts, audit, earnings, events
from app.services.errors import ConflictError, NotFoundError, ServiceError

UPI_ID = re.compile(r"^[A-Za-z0-9.\-_]{2,256}@[A-Za-z][A-Za-z0-9]{1,63}$")
MAX_AMOUNT = Decimal("100000")  # UPI's usual per-payment ceiling for most payers


def upi_id(db: Session, settings: Settings) -> str | None:
    """The owner's primary UPI ID from Settings, else MATT_UPI_ID from the environment."""
    saved = accounts.primary(db, settings, "upi")
    value = saved["number"] if saved else (settings.upi_id or "").strip()
    return value if UPI_ID.match(value) else None


def config(db: Session, settings: Settings) -> dict[str, Any]:
    vpa = upi_id(db, settings)
    bank = accounts.primary(db, settings, "bank")
    return {
        "money_rule": money.DIRECTION,
        "rule": "MATT only receives money, straight into your own UPI account. It never sends, "
        "transfers, withdraws, refunds or debits money.",
        "configured": vpa is not None or bank is not None,
        "bank": _bank_masked(bank),
        "upi_id": vpa,
        "payee_name": settings.upi_payee_name,
        "problem": None
        if vpa or bank or not settings.upi_id
        else "MATT_UPI_ID is not a valid UPI ID",
        "verification": "MATT cannot see your UPI account. Mark a request received once the "
        "money shows in your PhonePe app; only then is it counted as revenue.",
    }


def upi_link(vpa: str, payee: str, amount: Decimal, note: str, reference: str) -> str:
    params = {"pa": vpa, "pn": payee, "am": f"{amount:.2f}", "cu": "INR", "tn": note[:80],
              "tr": reference}  # fmt: skip
    return "upi://pay?" + urlencode(params, quote_via=quote)


def qr_svg(link: str) -> str:
    return str(segno.make(link, error="m").svg_inline(scale=4, border=2, dark="#000", light="#fff"))


def _bank_masked(bank: dict[str, Any] | None) -> dict[str, Any] | None:
    if bank is None:
        return None
    return {**bank, "number": f"•••• {bank['number'][-4:]}"}


def out(db: Session, row: PaymentRequest, settings: Settings) -> dict[str, Any]:
    has_upi = bool(row.upi_id)
    link = (
        upi_link(row.upi_id, settings.upi_payee_name, row.amount_inr, row.purpose, row.reference)
        if has_upi
        else None
    )
    return {
        # Full bank details: they are printed for the customer to pay into.
        "bank": accounts.primary(db, settings, "bank"),
        "id": row.id, "reference": row.reference, "amount_inr": row.amount_inr,
        "purpose": row.purpose, "customer_id": row.customer_id, "category": row.category,
        "status": row.status, "upi_id": row.upi_id or None, "upi_link": link,
        "qr_svg": qr_svg(link) if link else None,
        "ledger_entry_id": row.ledger_entry_id, "created_at": row.created_at,
        "received_at": row.received_at,
    }  # fmt: skip


def list_requests(db: Session) -> list[PaymentRequest]:
    stmt = select(PaymentRequest).order_by(PaymentRequest.id.desc()).limit(200)
    return list(db.scalars(stmt).all())


def create(
    db: Session, settings: Settings, user: User, *, amount_inr: Decimal, purpose: str,
    customer_id: int | None = None, category: str = RevenueCategory.OTHER,
) -> PaymentRequest:  # fmt: skip
    vpa = upi_id(db, settings)
    if vpa is None and accounts.primary(db, settings, "bank") is None:
        raise ServiceError(
            "Add where you get paid first: a UPI ID or bank account in Settings (or MATT_UPI_ID)"
        )
    money.refuse_outbound(purpose)
    if not (Decimal("1") <= amount_inr <= MAX_AMOUNT):
        raise ServiceError(f"Amount must be between ₹1 and ₹{MAX_AMOUNT:,.0f}")
    if customer_id is not None and db.get(Customer, customer_id) is None:
        raise NotFoundError("Customer not found")
    row = PaymentRequest(
        reference="pending", amount_inr=amount_inr, purpose=purpose.strip()[:300],
        customer_id=customer_id, category=RevenueCategory(category), status="requested",
        upi_id=vpa or "", created_by=str(user.id),
    )  # fmt: skip
    db.add(row)
    db.flush()
    row.reference = f"MATT{row.id:06d}"
    audit.record(
        db, actor_type="user", actor_id=str(user.id), action="payment_request.created",
        target_type="payment_request", target_id=str(row.id),
        details={"amount_inr": str(amount_inr), "reference": row.reference},
    )  # fmt: skip
    events.emit(db, "payment.requested", reference=row.reference, amount_inr=str(amount_inr))
    db.commit()
    return row


def _get(db: Session, request_id: int) -> PaymentRequest:
    row = db.get(PaymentRequest, request_id)
    if row is None:
        raise NotFoundError("Payment request not found")
    if row.status != "requested":
        raise ConflictError(f"Already {row.status}")
    return row


def mark_received(
    db: Session, user: User, request_id: int, *, received_on: date | None = None
) -> PaymentRequest:
    """The owner confirms the money is in their account: record it as revenue (a FACT)."""
    row = _get(db, request_id)
    row.status, row.received_at = "received", datetime.now(UTC)
    entry = earnings.record(
        db, user, kind="revenue", amount_inr=row.amount_inr,
        description=f"UPI payment {row.reference}: {row.purpose}"[:500],
        occurred_on=received_on or datetime.now(UTC).date(), category=row.category,
        customer_id=row.customer_id,
    )  # fmt: skip
    row.ledger_entry_id = entry.id
    events.emit(db, "payment.received", reference=row.reference, amount_inr=str(row.amount_inr))
    db.commit()
    return row


def cancel(db: Session, user: User, request_id: int) -> PaymentRequest:
    row = _get(db, request_id)
    row.status = "cancelled"
    audit.record(db, actor_type="user", actor_id=str(user.id), action="payment_request.cancelled",
                 target_type="payment_request", target_id=str(row.id), details={})  # fmt: skip
    db.commit()
    return row
