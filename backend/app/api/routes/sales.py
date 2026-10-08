"""Sales desk: ready offers to local businesses, sent by the owner, paid by UPI to the owner."""

from decimal import Decimal
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.api.deps import AppSettings, DbSession, Operator, Owner
from app.services import sales

router = APIRouter(prefix="/sales", tags=["sales"])


class PriceIn(BaseModel):
    amount_inr: Decimal = Field(ge=1, le=500_000, max_digits=12, decimal_places=2)


@router.get("")
def sales_desk(db: DbSession, _: Operator, settings: AppSettings) -> dict[str, Any]:
    return sales.desk(db, settings)


@router.post("/{lead_id}/price")
def set_price(
    lead_id: int, body: PriceIn, db: DbSession, user: Operator, settings: AppSettings
) -> dict[str, Any]:
    """Attach a UPI payment request in the owner's name; the offer text then includes it."""
    return sales.card(db, settings, sales.price(db, settings, user, lead_id, body.amount_inr))


@router.post("/{lead_id}/sent")
def offer_sent(
    lead_id: int, db: DbSession, user: Operator, settings: AppSettings
) -> dict[str, Any]:
    return sales.card(db, settings, sales.mark_sent(db, user, lead_id))


@router.post("/{lead_id}/paid")
def offer_paid(lead_id: int, db: DbSession, user: Owner, settings: AppSettings) -> dict[str, Any]:
    """Only the owner confirms the money is in their account; that records the revenue."""
    return sales.card(db, settings, sales.mark_paid(db, user, lead_id))
