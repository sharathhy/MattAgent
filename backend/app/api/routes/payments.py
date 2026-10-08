"""Receive-only UPI payment requests. There is deliberately no endpoint that moves money out."""

from datetime import date
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, status
from pydantic import BaseModel, Field

from app.api.deps import AppSettings, CurrentUser, DbSession, Operator, Owner
from app.core.domain import RevenueCategory
from app.services import payments

router = APIRouter(prefix="/payments", tags=["payments"])


class PaymentRequestIn(BaseModel):
    amount_inr: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    purpose: str = Field(min_length=2, max_length=300)
    customer_id: int | None = None
    category: RevenueCategory = RevenueCategory.OTHER


class ReceivedIn(BaseModel):
    received_on: date | None = None


@router.get("/config")
def payment_config(_: CurrentUser, settings: AppSettings) -> dict[str, Any]:
    return payments.config(settings)


@router.get("")
def list_payment_requests(
    db: DbSession, _: CurrentUser, settings: AppSettings
) -> list[dict[str, Any]]:
    return [payments.out(r, settings) for r in payments.list_requests(db)]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_payment_request(
    body: PaymentRequestIn, db: DbSession, user: Operator, settings: AppSettings
) -> dict[str, Any]:
    row = payments.create(db, settings, user, **body.model_dump())
    return payments.out(row, settings)


@router.post("/{request_id}/received")
def mark_payment_received(
    request_id: int, body: ReceivedIn, db: DbSession, user: Owner, settings: AppSettings
) -> dict[str, Any]:
    """Only the owner can confirm money arrived in their own account."""
    return payments.out(payments.mark_received(db, user, request_id, **body.model_dump()), settings)


@router.post("/{request_id}/cancel")
def cancel_payment_request(
    request_id: int, db: DbSession, user: Operator, settings: AppSettings
) -> dict[str, Any]:
    return payments.out(payments.cancel(db, user, request_id), settings)
