"""The owner's receiving accounts: where customers pay. Receive-only by design.

Only the owner can see or change these. Account numbers and UPI IDs are encrypted at rest,
shown masked, and every change is audit-logged. MATT never uses them to send or debit money;
they are only printed on payment requests so customers can pay the owner.
"""

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import crypto
from app.core.config import Settings
from app.models import ReceivingAccount, User
from app.services import audit, events
from app.services.errors import NotFoundError, ServiceError

IFSC = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")
ACCOUNT = re.compile(r"^\d{9,18}$")
UPI_ID = re.compile(r"^[A-Za-z0-9.\-_]{2,256}@[A-Za-z][A-Za-z0-9]{1,63}$")


def masked(row: ReceivingAccount) -> dict[str, Any]:
    return {
        "id": row.id, "kind": row.kind, "label": row.label, "holder_name": row.holder_name,
        "bank_name": row.bank_name, "ifsc": row.ifsc, "masked": f"•••• {row.last4}",
        "is_primary": row.is_primary, "updated_at": row.updated_at,
    }  # fmt: skip


def list_accounts(db: Session) -> list[ReceivingAccount]:
    return list(db.scalars(select(ReceivingAccount).order_by(ReceivingAccount.id)).all())


def _audit(db: Session, user: User, action: str, row: ReceivingAccount) -> None:
    audit.record(
        db, actor_type="user", actor_id=str(user.id), action=f"receiving_account.{action}",
        target_type="receiving_account", target_id=str(row.id),
        details={"kind": row.kind, "label": row.label, "last4": row.last4},
    )  # fmt: skip
    events.emit(db, f"receiving_account.{action}", kind=row.kind, label=row.label)


def add(
    db: Session, settings: Settings, user: User, *, kind: str, label: str, holder_name: str,
    number: str, bank_name: str | None = None, ifsc: str | None = None,
    is_primary: bool = False,
) -> ReceivingAccount:  # fmt: skip
    number = re.sub(r"\s+", "", number)
    if kind == "bank":
        ifsc = (ifsc or "").strip().upper()
        if not ACCOUNT.match(number):
            raise ServiceError("Account number must be 9 to 18 digits")
        if not IFSC.match(ifsc):
            raise ServiceError("IFSC must look like ABCD0123456")
        if not bank_name:
            raise ServiceError("Bank name is required")
    elif kind == "upi":
        if not UPI_ID.match(number):
            raise ServiceError("UPI ID must look like name@bank (a phone number alone won't work)")
        bank_name, ifsc = None, None
    else:
        raise ServiceError("Kind must be bank or upi")
    first_of_kind = not any(a.kind == kind for a in list_accounts(db))
    row = ReceivingAccount(
        kind=kind, label=label.strip()[:100], holder_name=holder_name.strip()[:200],
        bank_name=bank_name, ifsc=ifsc, secret_enc=crypto.encrypt(settings, number),
        last4=number[-4:], is_primary=False, created_by=str(user.id),
    )  # fmt: skip
    db.add(row)
    db.flush()
    if is_primary or first_of_kind:
        _make_primary(db, row)
    _audit(db, user, "added", row)
    db.commit()
    return row


def _make_primary(db: Session, row: ReceivingAccount) -> None:
    for other in list_accounts(db):
        if other.kind == row.kind:
            other.is_primary = other.id == row.id


def set_primary(db: Session, user: User, account_id: int) -> ReceivingAccount:
    row = _get(db, account_id)
    _make_primary(db, row)
    _audit(db, user, "made_primary", row)
    db.commit()
    return row


def remove(db: Session, user: User, account_id: int) -> None:
    row = _get(db, account_id)
    _audit(db, user, "removed", row)
    db.delete(row)
    db.commit()


def _get(db: Session, account_id: int) -> ReceivingAccount:
    row = db.get(ReceivingAccount, account_id)
    if row is None:
        raise NotFoundError("Account not found")
    return row


def primary(db: Session, settings: Settings, kind: str) -> dict[str, Any] | None:
    """Full details of the primary account of a kind, for printing on a payment request."""
    row = db.scalar(
        select(ReceivingAccount).where(ReceivingAccount.kind == kind, ReceivingAccount.is_primary)
    )
    if row is None:
        return None
    number = crypto.decrypt(settings, row.secret_enc)
    if number is None:
        return None
    return {"holder_name": row.holder_name, "bank_name": row.bank_name, "ifsc": row.ifsc,
            "number": number, "label": row.label}  # fmt: skip
