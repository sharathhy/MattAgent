"""What the API and worker call: the dashboard, owner controls, the demat section, the live gate."""

import math
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import crypto
from app.core.config import Settings
from app.llm.router import ModelRouter
from app.models import (
    BrokerAccount,
    MarketSnapshot,
    TradingAccount,
    TradingBot,
    TradingInsight,
    TradingTrade,
    User,
)
from app.services import audit, events
from app.services.errors import NotFoundError, ServiceError
from app.trading import clock, desk, strategies, swarm
from app.trading.broker import KITE_LOGIN, Broker, BrokerError, KiteBroker, KiteClient, PaperBroker
from app.trading.market import Feed, HttpFeed

LIVE_PHRASE = "I understand MATT can lose my real money"
ZERODHA_NEEDS = [
    "A Zerodha account with a demat and trading account, and a Kite Connect developer app "
    "(developers.kite.trade). The free Personal plan can place orders; MATT reads prices from "
    "free feeds, so the paid data plan isn't needed.",
    "Set the app's redirect URL to this site's /trading page, so the daily login returns here.",
    "A fresh Zerodha login every trading day: Kite access tokens expire each morning. Until you "
    "log in, live bots don't open anything.",
    "Kite Connect cannot withdraw or transfer money, and MATT never asks it to. Funds stay in "
    "your account; you add money to Zerodha yourself through their app.",
]


def _audit(db: Session, user: User, action: str, **details: Any) -> None:
    audit.record(
        db,
        actor_type="user",
        actor_id=str(user.id),
        action=f"trading.{action}",
        target_type="trading_account",
        target_id="1",
        details={k: str(v) for k, v in details.items()},
    )
    events.emit(db, f"trading.{action}", by=str(user.id))


# --- Worker --------------------------------------------------------------------------------


def broker_for(db: Session, settings: Settings, acct: TradingAccount, now: datetime) -> Broker:
    if acct.mode != "live":
        return PaperBroker()
    row = connected_broker(db, now)
    if row is None:
        acct.halted_reason = "Live mode needs today's Zerodha login before bots can trade"
        acct.halted_day = clock.trading_day(now)
        return PaperBroker()
    if acct.halted_reason and acct.halted_reason.startswith("Live mode needs"):
        acct.halted_reason, acct.halted_day = None, None
    api_key = crypto.decrypt(settings, row.api_key_enc) or ""
    token = crypto.decrypt(settings, row.access_token_enc or "") or ""
    return KiteBroker(KiteClient(api_key, token))


def tick(
    db: Session, router: ModelRouter, *, feed: Feed | None = None, now: datetime | None = None
) -> dict[str, int]:
    now = now or datetime.now(UTC)
    settings = router.settings
    acct = desk.account(db)
    broker = broker_for(db, settings, acct, now)
    return swarm.tick(db, router, feed or HttpFeed(settings.usd_to_inr), broker, now=now)


# --- Dashboard -----------------------------------------------------------------------------


def _trade(t: TradingTrade) -> dict[str, Any]:
    unreal = None
    if t.status == "open" and t.last_price is not None:
        unreal = float((t.last_price - t.entry_price) * t.qty * (1 if t.side == "long" else -1))
    return {
        "id": t.id,
        "mode": t.mode,
        "symbol": t.symbol,
        "market": t.market,
        "side": t.side,
        "qty": float(t.qty),
        "entry_price": float(t.entry_price),
        "stop_price": float(t.stop_price),
        "target_price": float(t.target_price),
        "last_price": float(t.last_price or t.entry_price),
        "exit_price": float(t.exit_price) if t.exit_price is not None else None,
        "status": t.status,
        "exit_reason": t.exit_reason,
        "pnl": float(t.pnl),
        "fees": float(t.fees),
        "unrealized": unreal,
        "strategy": t.strategy,
        "opened_at": t.opened_at,
        "closed_at": t.closed_at,
    }


def _bot(b: TradingBot) -> dict[str, Any]:
    return {
        "slug": b.slug,
        "name": b.name,
        "role": b.role,
        "symbol": b.symbol,
        "strategy": b.strategy,
        "generation": b.generation,
        "runs": b.runs,
        "trades": b.trades,
        "wins": b.wins,
        "losses": b.losses,
        "pnl": float(b.pnl),
        "fitness": b.fitness,
        "last_run_at": b.last_run_at,
        "last_note": b.last_note,
        "avoid": b.memory.get("avoid", []),
        "backtest": b.memory.get("backtest"),
    }


def stats(db: Session, mode: str) -> dict[str, Any]:
    closed = db.scalars(
        select(TradingTrade).where(TradingTrade.status == "closed", TradingTrade.mode == mode)
    ).all()
    wins = [float(t.pnl) for t in closed if t.pnl > 0]
    losses = [float(t.pnl) for t in closed if t.pnl <= 0]
    n = len(closed)
    return {
        "trades": n,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(len(wins) / n, 3) if n else None,
        "avg_win": round(sum(wins) / len(wins), 4) if wins else None,
        "avg_loss": round(sum(losses) / len(losses), 4) if losses else None,
        "expectancy": round((sum(wins) + sum(losses)) / n, 4) if n else None,
    }


def overview(db: Session, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    swarm.ensure_bots(db)
    acct = desk.account(db)
    eq = desk.equity(db, acct)
    goal = acct.goal_inr
    recent = now - timedelta(minutes=15)
    roles = []
    for role, total in swarm.ROLE_COUNTS.items():
        active = db.scalar(
            select(func.count())
            .select_from(TradingBot)
            .where(TradingBot.role == role, TradingBot.last_run_at >= recent)
        )
        roles.append({"role": role, "bots": total, "active_15m": int(active or 0)})
    top = db.scalars(
        select(TradingBot)
        .where(TradingBot.role == "strategist")
        .order_by(TradingBot.fitness.desc())
        .limit(10)
    ).all()
    traders = db.scalars(
        select(TradingBot)
        .where(TradingBot.role == "trader", TradingBot.last_run_at.is_not(None))
        .order_by(TradingBot.last_run_at.desc())
        .limit(8)
    ).all()
    snaps = db.scalars(
        select(MarketSnapshot)
        .where(MarketSnapshot.interval == "5m")
        .order_by(MarketSnapshot.symbol)
    ).all()

    def insights(kind: str, n: int) -> list[dict[str, Any]]:
        rows = db.scalars(
            select(TradingInsight)
            .where(TradingInsight.kind == kind)
            .order_by(TradingInsight.created_at.desc())
            .limit(n)
        ).all()
        return [
            {
                "id": r.id,
                "symbol": r.symbol,
                "title": r.title,
                "url": r.url,
                "sentiment": r.sentiment,
                "content": r.content,
                "created_at": r.created_at,
            }
            for r in rows
        ]

    trades = db.scalars(
        select(TradingTrade)
        .where(TradingTrade.status == "closed")
        .order_by(TradingTrade.id.desc())
        .limit(30)
    ).all()
    return {
        "account": {
            "mode": acct.mode,
            "enabled": acct.enabled,
            "kill_switch": acct.kill_switch,
            "halted_reason": acct.halted_reason,
            "blocked": desk.blocked(acct),
            "starting_capital": float(acct.starting_capital),
            "cash": float(acct.cash),
            "equity": float(eq),
            "realized_pnl": float(acct.realized_pnl),
            "fees_paid": float(acct.fees_paid),
            "day_pnl": float(eq - acct.day_start_equity),
            "total_return_pct": round(
                float((eq - acct.starting_capital) / acct.starting_capital * 100), 3
            )
            if acct.starting_capital
            else 0.0,
            "peak_equity": float(acct.peak_equity),
            "goal_inr": float(goal),
            "doublings_to_goal": round(math.log2(float(goal) / float(eq)), 1) if eq > 0 else None,
            "max_trade_risk_pct": acct.max_trade_risk_pct,
            "max_day_loss_pct": acct.max_day_loss_pct,
            "max_open_positions": acct.max_open_positions,
            "live_capital_cap_inr": float(acct.live_capital_cap_inr),
            "live_confirmed_at": acct.live_confirmed_at,
            "last_tick_at": acct.last_tick_at,
            "nse_open": clock.nse_open(now),
        },
        "curve": acct.equity_curve or [],
        "positions": [_trade(t) for t in desk.open_trades(db)],
        "trades": [_trade(t) for t in trades],
        "stats": {"paper": stats(db, "paper"), "live": stats(db, "live")},
        "roles": roles,
        "top_strategists": [_bot(b) for b in top],
        "traders": [_bot(b) for b in traders],
        "market": [
            {
                "symbol": s.symbol,
                "market": s.market,
                "price": float(s.price_inr),
                "change_pct": s.change_pct,
                "trend": s.indicators.get("trend"),
                "rsi": s.indicators.get("rsi"),
                "above_vwap": s.indicators.get("price", 0) > s.indicators.get("vwap", 0),
                "patterns": s.patterns,
                "updated_at": s.updated_at,
            }
            for s in snaps
        ],
        "news": insights("news", 15),
        "research": insights("research", 10),
        "lessons": insights("lesson", 10),
        "strategies": strategies.describe(),
        "live_phrase": LIVE_PHRASE,
        "broker_needs": ZERODHA_NEEDS,
    }


def account_view(db: Session) -> dict[str, Any]:
    view: dict[str, Any] = overview(db)["account"]
    return view


def bots(db: Session, role: str | None) -> list[dict[str, Any]]:
    swarm.ensure_bots(db)
    stmt = select(TradingBot).order_by(TradingBot.id)
    if role:
        stmt = stmt.where(TradingBot.role == role)
    return [_bot(b) for b in db.scalars(stmt).all()]


# --- Owner controls ------------------------------------------------------------------------

EDITABLE = {
    "enabled",
    "max_trade_risk_pct",
    "max_day_loss_pct",
    "max_open_positions",
    "live_capital_cap_inr",
}


def update(db: Session, user: User, changes: dict[str, Any]) -> TradingAccount:
    acct = desk.account(db)
    for key in ("max_trade_risk_pct", "max_day_loss_pct"):
        if key in changes and not (0.1 <= float(changes[key]) <= desk.HARD_MAX_PCT):
            raise ServiceError(f"{key} must be between 0.1 and {desk.HARD_MAX_PCT:g}")
    if "max_open_positions" in changes and not (1 <= int(changes["max_open_positions"]) <= 10):
        raise ServiceError("max_open_positions must be 1 to 10")
    for key, value in changes.items():
        if key in EDITABLE:
            setattr(acct, key, Decimal(str(value)) if key == "live_capital_cap_inr" else value)
    _audit(db, user, "settings_updated", **changes)
    db.commit()
    return acct


def kill(
    db: Session, user: User, router: ModelRouter, now: datetime | None = None
) -> TradingAccount:
    """Owner's stop switch: block new trades and square off everything now."""
    now = now or datetime.now(UTC)
    acct = desk.account(db)
    acct.kill_switch = True
    _audit(db, user, "kill_switch_on")
    db.commit()
    broker = broker_for(db, router.settings, acct, now)
    for trade in desk.open_trades(db):
        price = float(trade.last_price or trade.entry_price)
        desk.close_trade(db, acct, broker, trade, price, "kill_switch", now)
    db.commit()
    return acct


def resume(db: Session, user: User) -> TradingAccount:
    acct = desk.account(db)
    acct.kill_switch, acct.enabled = False, True
    if acct.halted_reason and not acct.halted_reason.startswith("Daily loss"):
        acct.halted_reason, acct.halted_day = None, None
    _audit(db, user, "resumed")
    db.commit()
    return acct


def _reset_ledger(acct: TradingAccount, capital: Decimal) -> None:
    acct.starting_capital = acct.cash = acct.peak_equity = acct.day_start_equity = capital
    acct.realized_pnl = acct.fees_paid = Decimal("0")
    acct.equity_curve, acct.halted_reason, acct.halted_day = [], None, None


def reset_paper(db: Session, user: User) -> TradingAccount:
    acct = desk.account(db)
    if acct.mode != "paper":
        raise ServiceError("Switch back to paper mode first")
    if desk.open_trades(db, "paper"):
        raise ServiceError("Close open paper positions first (use Stop trading)")
    _reset_ledger(acct, desk.PAPER_CAPITAL)
    _audit(db, user, "paper_reset")
    db.commit()
    return acct


def go_live(
    db: Session, user: User, confirm: str, capital_cap_inr: Decimal, now: datetime | None = None
) -> TradingAccount:
    """The owner switches real trading on. Needs the exact phrase, a connected broker with
    today's login, a capital cap, and no open paper positions."""
    now = now or datetime.now(UTC)
    acct = desk.account(db)
    if confirm.strip().lower() != LIVE_PHRASE.lower():
        raise ServiceError(f'Type exactly: "{LIVE_PHRASE}"')
    row = connected_broker(db, now)
    if row is None:
        raise ServiceError("Connect Zerodha and complete today's login first")
    if capital_cap_inr <= 0:
        raise ServiceError("Set how much real money MATT may trade with")
    if row.funds_inr is not None and capital_cap_inr > row.funds_inr:
        raise ServiceError(
            f"Your Zerodha account shows ₹{row.funds_inr} available; set a cap at or below it"
        )
    if desk.open_trades(db):
        raise ServiceError("Close open positions first (use Stop trading)")
    acct.mode, acct.live_capital_cap_inr = "live", capital_cap_inr
    acct.live_confirmed_at, acct.live_confirmed_by = now, str(user.id)
    acct.kill_switch, acct.enabled = False, True
    _reset_ledger(acct, capital_cap_inr)
    acct.day = clock.trading_day(now)
    _audit(db, user, "live_on", capital_cap_inr=capital_cap_inr, phrase=confirm.strip())
    db.commit()
    return acct


def go_paper(db: Session, user: User) -> TradingAccount:
    acct = desk.account(db)
    if desk.open_trades(db, "live"):
        raise ServiceError("Close live positions first (use Stop trading)")
    acct.mode, acct.live_confirmed_at, acct.live_confirmed_by = "paper", None, None
    _reset_ledger(acct, desk.PAPER_CAPITAL)
    _audit(db, user, "live_off")
    db.commit()
    return acct


# --- Demat / broker ------------------------------------------------------------------------


def broker_out(row: BrokerAccount, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    logged_in = row.status == "connected" and row.token_day == clock.trading_day(now)
    return {
        "id": row.id,
        "broker": row.broker,
        "label": row.label,
        "client_id": row.client_id,
        "status": "connected" if logged_in else "needs_login",
        "funds_inr": float(row.funds_inr) if row.funds_inr is not None else None,
        "last_error": row.last_error,
        "updated_at": row.updated_at,
    }


def brokers(db: Session) -> list[BrokerAccount]:
    return list(db.scalars(select(BrokerAccount).order_by(BrokerAccount.id)).all())


def connected_broker(db: Session, now: datetime) -> BrokerAccount | None:
    today = clock.trading_day(now)
    return next((b for b in brokers(db) if b.status == "connected" and b.token_day == today), None)


def add_broker(
    db: Session,
    settings: Settings,
    user: User,
    *,
    label: str,
    client_id: str,
    api_key: str,
    api_secret: str,
) -> BrokerAccount:
    if brokers(db):
        raise ServiceError("A broker is already connected; remove it first")
    row = BrokerAccount(
        broker="zerodha",
        label=label.strip()[:100],
        client_id=client_id.strip().upper()[:50],
        api_key_enc=crypto.encrypt(settings, api_key.strip()),
        api_secret_enc=crypto.encrypt(settings, api_secret.strip()),
        status="needs_login",
        created_by=str(user.id),
    )
    db.add(row)
    db.flush()
    _audit(db, user, "broker_added", broker="zerodha", client_id=row.client_id)
    db.commit()
    return row


def _get_broker(db: Session, broker_id: int) -> BrokerAccount:
    row = db.get(BrokerAccount, broker_id)
    if row is None:
        raise NotFoundError("Broker not found")
    return row


def login_url(db: Session, settings: Settings, broker_id: int) -> str:
    row = _get_broker(db, broker_id)
    return KITE_LOGIN.format(api_key=crypto.decrypt(settings, row.api_key_enc) or "")


def complete_login(
    db: Session,
    settings: Settings,
    user: User,
    broker_id: int,
    request_token: str,
    client: KiteClient | None = None,
    now: datetime | None = None,
) -> BrokerAccount:
    now = now or datetime.now(UTC)
    row = _get_broker(db, broker_id)
    api_key = crypto.decrypt(settings, row.api_key_enc)
    secret = crypto.decrypt(settings, row.api_secret_enc)
    if not api_key or not secret:
        raise ServiceError(
            "Saved keys can't be read (the server secret changed); re-add the broker"
        )
    kite = client or KiteClient(api_key)
    try:
        token = kite.create_session(request_token.strip(), secret)
        funds = kite.funds()
    except BrokerError as exc:
        row.status, row.last_error = "error", str(exc)[:500]
        db.commit()
        raise ServiceError(f"Zerodha login failed: {exc}") from exc
    row.access_token_enc = crypto.encrypt(settings, token)
    row.token_day, row.status, row.last_error = clock.trading_day(now), "connected", None
    row.funds_inr = Decimal(str(round(funds, 2)))
    _audit(db, user, "broker_login", client_id=row.client_id)
    db.commit()
    return row


def remove_broker(db: Session, user: User, broker_id: int) -> None:
    row = _get_broker(db, broker_id)
    acct = desk.account(db)
    if acct.mode == "live":
        raise ServiceError("Switch back to paper mode before removing the broker")
    _audit(db, user, "broker_removed", client_id=row.client_id)
    db.delete(row)
    db.commit()


def spoken_status(db: Session) -> str:
    view = overview(db)
    a = view["account"]
    s = view["stats"][a["mode"]]
    won = (
        f"{s['win_rate']:.0%} of {s['trades']} trades won"
        if s["trades"]
        else "no trades closed yet"
    )
    state = f" Trading is blocked: {a['blocked']}." if a["blocked"] else ""
    return (
        f"{a['mode'].title()} trading: balance ₹{a['equity']:.2f} from "
        f"₹{a['starting_capital']:.2f} ({a['total_return_pct']:+.2f}%), today "
        f"₹{a['day_pnl']:+.2f}, {won}, {len(view['positions'])} open position(s).{state}"
    )
