"""Receive-only UPI payment requests. There is deliberately no endpoint that moves money out."""

from datetime import date
from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, status
from pydantic import BaseModel, Field

from app.api.deps import AppSettings, CurrentUser, DbSession, Operator, Owner
from app.core.domain import RevenueCategory
from app.services import accounts, payments

router = APIRouter(prefix="/payments", tags=["payments"])


class PaymentRequestIn(BaseModel):
    amount_inr: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    purpose: str = Field(min_length=2, max_length=300)
    customer_id: int | None = None
    category: RevenueCategory = RevenueCategory.OTHER


class ReceivedIn(BaseModel):
    received_on: date | None = None


@router.get("/config")
def payment_config(db: DbSession, _: CurrentUser, settings: AppSettings) -> dict[str, Any]:
    return payments.config(db, settings)


@router.get("")
def list_payment_requests(
    db: DbSession, _: Operator, settings: AppSettings
) -> list[dict[str, Any]]:
    return [payments.out(db, r, settings) for r in payments.list_requests(db)]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_payment_request(
    body: PaymentRequestIn, db: DbSession, user: Operator, settings: AppSettings
) -> dict[str, Any]:
    row = payments.create(db, settings, user, **body.model_dump())
    return payments.out(db, row, settings)


@router.post("/{request_id}/received")
def mark_payment_received(
    request_id: int, body: ReceivedIn, db: DbSession, user: Owner, settings: AppSettings
) -> dict[str, Any]:
    """Only the owner can confirm money arrived in their own account."""
    row = payments.mark_received(db, user, request_id, **body.model_dump())
    return payments.out(db, row, settings)


@router.post("/{request_id}/cancel")
def cancel_payment_request(
    request_id: int, db: DbSession, user: Operator, settings: AppSettings
) -> dict[str, Any]:
    return payments.out(db, payments.cancel(db, user, request_id), settings)


# --- Where the owner gets paid (owner only; encrypted, masked, audit-logged) ---


class AccountIn(BaseModel):
    kind: Literal["bank", "upi"]
    label: str = Field(min_length=1, max_length=100)
    holder_name: str = Field(min_length=2, max_length=200)
    number: str = Field(min_length=3, max_length=300, description="Account number or UPI ID")
    bank_name: str | None = Field(default=None, max_length=200)
    ifsc: str | None = Field(default=None, max_length=11)
    is_primary: bool = False


@router.get("/accounts")
def list_accounts(db: DbSession, _: Owner) -> list[dict[str, Any]]:
    return [accounts.masked(a) for a in accounts.list_accounts(db)]


@router.post("/accounts", status_code=status.HTTP_201_CREATED)
def add_account(
    body: AccountIn, db: DbSession, user: Owner, settings: AppSettings
) -> dict[str, Any]:
    return accounts.masked(accounts.add(db, settings, user, **body.model_dump()))


@router.post("/accounts/{account_id}/primary")
def make_primary(account_id: int, db: DbSession, user: Owner) -> dict[str, Any]:
    return accounts.masked(accounts.set_primary(db, user, account_id))


@router.delete("/accounts/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_account(account_id: int, db: DbSession, user: Owner) -> None:
    accounts.remove(db, user, account_id)
