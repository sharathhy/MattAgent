"""Sales desk: ready offers to local businesses, sent by the owner, paid by UPI to the owner."""

from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.api.deps import AppSettings, DbSession, Operator, Owner, Router
from app.services import sales

router = APIRouter(prefix="/sales", tags=["sales"])


class SampleIn(BaseModel):
    service: str = Field(default="website", max_length=40)


class PriceIn(BaseModel):
    amount_inr: Decimal = Field(ge=1, le=500_000, max_digits=12, decimal_places=2)


@router.get("/services")
def services(_: Operator) -> list[dict[str, Any]]:
    """What MATT can sell, each with the free sample it builds first."""
    return sales.catalog()


@router.get("")
def sales_desk(
    request: Request, db: DbSession, _: Operator, settings: AppSettings
) -> dict[str, Any]:
    return sales.desk(db, settings, str(request.base_url))


@router.post("/{lead_id}/price")
def set_price(
    lead_id: int,
    body: PriceIn,
    request: Request,
    db: DbSession,
    user: Operator,
    settings: AppSettings,
) -> dict[str, Any]:
    """Attach a UPI payment request in the owner's name; the offer text then includes it."""
    return sales.card(
        db,
        settings,
        sales.price(db, settings, user, lead_id, body.amount_inr),
        str(request.base_url),
    )


@router.post("/{lead_id}/sent")
def offer_sent(
    lead_id: int, request: Request, db: DbSession, user: Operator, settings: AppSettings
) -> dict[str, Any]:
    return sales.card(db, settings, sales.mark_sent(db, user, lead_id), str(request.base_url))


@router.post("/{lead_id}/paid")
def offer_paid(
    lead_id: int, request: Request, db: DbSession, user: Owner, settings: AppSettings
) -> dict[str, Any]:
    """Only the owner confirms the money is in their account; that records the revenue."""
    return sales.card(db, settings, sales.mark_paid(db, user, lead_id), str(request.base_url))


@router.post("/{lead_id}/demo")
def build_demo(
    lead_id: int,
    request: Request,
    db: DbSession,
    _: Operator,
    settings: AppSettings,
    model_router: Router,
    body: SampleIn | None = None,
) -> dict[str, Any]:
    """Build (or rebuild) the free sample of a service for this business and add its link."""
    service = body.service if body else "website"
    lead = sales.make_demo(db, model_router, settings, lead_id, service)
    return sales.card(db, settings, lead, str(request.base_url))
