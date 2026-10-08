"""Trading desk: dashboard for everyone signed in; controls, demat and the live switch are
owner-only. The only money-moving path is order placement in the owner's own demat account."""

from decimal import Decimal
from typing import Any

from fastapi import APIRouter, status
from pydantic import BaseModel, Field

from app.api.deps import AppSettings, CurrentUser, DbSession, Operator, Owner, Router
from app.trading import service

router = APIRouter(prefix="/trading", tags=["trading"])


@router.get("")
def overview(db: DbSession, _: CurrentUser) -> dict[str, Any]:
    return service.overview(db)


@router.get("/bots")
def list_bots(db: DbSession, _: CurrentUser, role: str | None = None) -> list[dict[str, Any]]:
    return service.bots(db, role)


class SettingsIn(BaseModel):
    enabled: bool | None = None
    max_trade_risk_pct: float | None = Field(default=None, ge=0.1, le=20)
    max_day_loss_pct: float | None = Field(default=None, ge=0.1, le=20)
    max_open_positions: int | None = Field(default=None, ge=1, le=10)
    live_capital_cap_inr: Decimal | None = Field(
        default=None, ge=0, max_digits=14, decimal_places=2
    )


@router.patch("/settings")
def update_settings(body: SettingsIn, db: DbSession, user: Owner) -> dict[str, Any]:
    service.update(db, user, body.model_dump(exclude_none=True))
    return service.account_view(db)


@router.post("/stop")
def stop(db: DbSession, user: Operator, router_: Router) -> dict[str, Any]:
    """Kill switch: anyone who can operate MATT may stop trading; only the owner can resume."""
    service.kill(db, user, router_)
    return service.account_view(db)


@router.post("/resume")
def resume(db: DbSession, user: Owner) -> dict[str, Any]:
    service.resume(db, user)
    return service.account_view(db)


@router.post("/paper/reset")
def reset_paper(db: DbSession, user: Owner) -> dict[str, Any]:
    service.reset_paper(db, user)
    return service.account_view(db)


class LiveIn(BaseModel):
    confirm: str = Field(max_length=200)
    capital_cap_inr: Decimal = Field(gt=0, max_digits=14, decimal_places=2)


@router.post("/live")
def go_live(body: LiveIn, db: DbSession, user: Owner) -> dict[str, Any]:
    service.go_live(db, user, body.confirm, body.capital_cap_inr)
    return service.account_view(db)


@router.post("/paper")
def go_paper(db: DbSession, user: Owner) -> dict[str, Any]:
    service.go_paper(db, user)
    return service.account_view(db)


# --- Demat / broker (owner only; keys encrypted, never returned) ---


class BrokerIn(BaseModel):
    label: str = Field(min_length=1, max_length=100)
    client_id: str = Field(min_length=2, max_length=50)
    api_key: str = Field(min_length=4, max_length=200)
    api_secret: str = Field(min_length=4, max_length=200)


class LoginIn(BaseModel):
    request_token: str = Field(min_length=4, max_length=200)


@router.get("/brokers")
def list_brokers(db: DbSession, _: Owner) -> dict[str, Any]:
    return {"brokers": [service.broker_out(b) for b in service.brokers(db)],
            "needs": service.ZERODHA_NEEDS}  # fmt: skip


@router.post("/brokers", status_code=status.HTTP_201_CREATED)
def add_broker(body: BrokerIn, db: DbSession, user: Owner, settings: AppSettings) -> dict[str, Any]:
    return service.broker_out(service.add_broker(db, settings, user, **body.model_dump()))


@router.get("/brokers/{broker_id}/login")
def broker_login_url(
    broker_id: int, db: DbSession, _: Owner, settings: AppSettings
) -> dict[str, str]:
    return {"url": service.login_url(db, settings, broker_id)}


@router.post("/brokers/{broker_id}/login")
def broker_login(
    broker_id: int, body: LoginIn, db: DbSession, user: Owner, settings: AppSettings
) -> dict[str, Any]:
    row = service.complete_login(db, settings, user, broker_id, body.request_token)
    return service.broker_out(row)


@router.delete("/brokers/{broker_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_broker(broker_id: int, db: DbSession, user: Owner) -> None:
    service.remove_broker(db, user, broker_id)
