"""The trading desk: one account, hard risk limits, opening and closing positions.

Hard limits, enforced here for every trade, paper or live:
- intraday cash only (no futures, options or leverage), so the balance can't go below zero;
- each trade risks at most ``max_trade_risk_pct`` of equity (owner-set, never above 20%);
- after a ``max_day_loss_pct`` loss in a day (never above 20%) everything is squared off and
  nothing new opens until the next day;
- every position is squared off before the market closes;
- the owner's kill switch squares off everything and blocks new trades until they resume;
- live mode never risks more than the owner's capital cap, and every order is audit-logged.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import ROUND_DOWN, Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import TradingAccount, TradingBot, TradingTrade
from app.services import audit, events
from app.trading import backtest, clock, costs
from app.trading.broker import Broker, BrokerError
from app.trading.universe import BY_SYMBOL, Instrument

PAPER_CAPITAL = Decimal("100")
GOAL_INR = Decimal("1000000000")  # ₹100 crore: the owner's stated aim, not a forecast
HARD_MAX_PCT = 20.0
CURVE_EVERY = timedelta(minutes=5)
ACTOR = "trading-desk"


def account(db: Session) -> TradingAccount:
    row = db.scalar(select(TradingAccount).limit(1))
    if row is None:
        row = TradingAccount(
            mode="paper", enabled=True, kill_switch=False, starting_capital=PAPER_CAPITAL,
            cash=PAPER_CAPITAL, realized_pnl=Decimal("0"), fees_paid=Decimal("0"),
            peak_equity=PAPER_CAPITAL, day_start_equity=PAPER_CAPITAL, goal_inr=GOAL_INR,
            max_trade_risk_pct=2.0, max_day_loss_pct=HARD_MAX_PCT, max_open_positions=3,
            live_capital_cap_inr=Decimal("0"), bot_cursor=0, equity_curve=[],
        )  # fmt: skip
        db.add(row)
        db.commit()
    return row


def open_trades(db: Session, mode: str | None = None) -> list[TradingTrade]:
    stmt = select(TradingTrade).where(TradingTrade.status == "open")
    if mode:
        stmt = stmt.where(TradingTrade.mode == mode)
    return list(db.scalars(stmt.order_by(TradingTrade.id)).all())


def _value(t: TradingTrade) -> Decimal:
    """What an open position is worth now: the cash reserved plus unrealised profit."""
    last = t.last_price or t.entry_price
    gross = (last - t.entry_price) * t.qty * (1 if t.side == "long" else -1)
    return t.entry_price * t.qty + gross


def equity(db: Session, acct: TradingAccount) -> Decimal:
    return acct.cash + sum((_value(t) for t in open_trades(db, acct.mode)), Decimal("0"))


def roll_day(db: Session, acct: TradingAccount, now: datetime) -> None:
    today = clock.trading_day(now)
    if acct.day != today:
        acct.day = today
        acct.day_start_equity = equity(db, acct)
        if acct.halted_day and acct.halted_day != today:
            acct.halted_reason, acct.halted_day = None, None  # a daily halt ends with the day


def blocked(acct: TradingAccount) -> str | None:
    """Why no new position may open right now, or None."""
    if acct.kill_switch:
        return "Kill switch is on"
    if not acct.enabled:
        return "Trading is paused"
    if acct.halted_reason:
        return acct.halted_reason
    return None


def check_day_loss(db: Session, acct: TradingAccount, eq: Decimal) -> bool:
    limit = acct.day_start_equity * Decimal(str(1 - min(acct.max_day_loss_pct, HARD_MAX_PCT) / 100))
    if eq <= limit and not acct.halted_reason:
        acct.halted_reason = (
            f"Daily loss limit hit ({acct.max_day_loss_pct:g}% of the day's starting balance); "
            "everything was squared off and trading resumes tomorrow"
        )
        acct.halted_day = acct.day
        events.emit(db, "trading.halted", reason=acct.halted_reason, equity=str(eq))
        return True
    return False


@dataclass(frozen=True)
class Order:
    inst: Instrument
    side: int  # +1 long, -1 short
    price: float
    atr: float
    params: dict[str, float]
    features: dict[str, Any]
    strategy: str | None
    trader: TradingBot | None
    strategist: TradingBot | None


def size(acct: TradingAccount, eq: Decimal, order: Order, open_count: int) -> tuple[Decimal, float, float]:
    """(quantity, stop, target). Quantity is 0 when the trade can't be sized within the limits."""
    stop, target = backtest.levels(order.side, order.price, order.atr, order.params)
    dist = Decimal(str(abs(order.price - stop)))
    if dist <= 0:
        return Decimal("0"), stop, target
    risk_pct = Decimal(str(min(acct.max_trade_risk_pct, HARD_MAX_PCT) / 100))
    qty = eq * risk_pct / dist
    slots = max(acct.max_open_positions - open_count, 1)
    budget = acct.cash / slots
    if acct.mode == "live":
        budget = min(budget, acct.live_capital_cap_inr)
    qty = min(qty, budget / Decimal(str(order.price)))
    step = Decimal("0.000001") if order.inst.fractional else Decimal("1")
    qty = qty.quantize(step, rounding=ROUND_DOWN)
    if qty * Decimal(str(order.price)) < Decimal("1"):
        return Decimal("0"), stop, target
    return qty, stop, target


def open_trade(
    db: Session, acct: TradingAccount, broker: Broker, order: Order, now: datetime
) -> TradingTrade | None:
    if blocked(acct) or not clock.can_enter(order.inst.market, now):
        return None
    if acct.mode == "live" and order.inst.market != "nse":
        return None  # crypto isn't held in a demat account; live mode trades NSE only
    if order.side < 0 and order.inst.market == "crypto":
        return None  # spot crypto can't be sold short
    current = open_trades(db, acct.mode)
    if len(current) >= acct.max_open_positions or any(t.symbol == order.inst.symbol for t in current):
        return None
    eq = equity(db, acct)
    qty, stop, target = size(acct, eq, order, len(current))
    if qty <= 0:
        return None
    entry = Decimal(str(round(order.price, 4)))
    side = "long" if order.side > 0 else "short"
    orders: dict[str, Any] = {}
    if broker.live:
        try:
            orders = broker.enter(order.inst.symbol, side, int(qty), stop)
        except BrokerError as exc:
            events.emit(db, "trading.order_rejected", symbol=order.inst.symbol, error=str(exc))
            audit.record(db, actor_type="system", actor_id=ACTOR, action="trading.order_rejected",
                         target_type="symbol", target_id=order.inst.symbol,
                         details={"side": side, "qty": str(qty), "error": str(exc)})  # fmt: skip
            db.commit()
            return None
        entry = Decimal(str(orders.get("fill_price") or entry))
    trade = TradingTrade(
        mode=acct.mode, symbol=order.inst.symbol, market=order.inst.market, side=side, qty=qty,
        entry_price=entry, stop_price=Decimal(str(round(stop, 4))),
        target_price=Decimal(str(round(target, 4))), last_price=entry, status="open",
        trader_bot_id=order.trader.id if order.trader else None,
        strategist_bot_id=order.strategist.id if order.strategist else None,
        strategy=order.strategy, features=order.features, broker_orders=orders, opened_at=now,
        pnl=Decimal("0"), fees=Decimal("0"),
    )  # fmt: skip
    db.add(trade)
    acct.cash -= entry * qty
    db.flush()
    audit.record(db, actor_type="system", actor_id=ACTOR, action=f"trading.{acct.mode}.open",
                 target_type="trade", target_id=str(trade.id),
                 details={"symbol": trade.symbol, "side": side, "qty": str(qty),
                          "entry": str(entry), "stop": str(trade.stop_price),
                          "target": str(trade.target_price), "orders": orders})  # fmt: skip
    events.emit(db, "trading.opened", trade_id=trade.id, symbol=trade.symbol, side=side,
                qty=str(qty), price=str(entry), mode=acct.mode)  # fmt: skip
    return trade


def close_trade(
    db: Session, acct: TradingAccount, broker: Broker, trade: TradingTrade, price: float,
    reason: str, now: datetime,
) -> TradingTrade:  # fmt: skip
    exit_price = Decimal(str(round(price, 4)))
    if trade.mode == "live" and not broker.live:
        # No broker session today: MATT can't close a real position, so it doesn't pretend to.
        # The stop-loss order held at Zerodha and Zerodha's own square-off still protect it.
        events.emit(db, "trading.exit_pending", trade_id=trade.id, reason=reason)
        return trade
    if broker.live and trade.mode == "live":
        try:
            result = broker.exit(trade.symbol, trade.side, int(trade.qty), trade.broker_orders)
            exit_price = Decimal(str(result.get("fill_price") or exit_price))
            trade.broker_orders = {**trade.broker_orders, **result}
        except BrokerError as exc:
            # Leave it open and say so loudly; the broker's own stop order still protects it.
            events.emit(db, "trading.exit_failed", trade_id=trade.id, error=str(exc))
            audit.record(db, actor_type="system", actor_id=ACTOR, action="trading.exit_failed",
                         target_type="trade", target_id=str(trade.id),
                         details={"error": str(exc)})  # fmt: skip
            return trade
    direction = 1 if trade.side == "long" else -1
    gross = (exit_price - trade.entry_price) * trade.qty * direction
    buy_value = float(trade.entry_price * trade.qty if direction > 0 else exit_price * trade.qty)
    sell_value = float(exit_price * trade.qty if direction > 0 else trade.entry_price * trade.qty)
    fees = Decimal(str(round(costs.round_trip(trade.market, buy_value, sell_value), 4)))
    trade.exit_price, trade.last_price, trade.status = exit_price, exit_price, "closed"
    trade.exit_reason, trade.closed_at = reason, now
    trade.fees, trade.pnl = fees, gross - fees
    acct.cash += trade.entry_price * trade.qty + gross - fees
    acct.realized_pnl += trade.pnl
    acct.fees_paid += fees
    for bot_id in {trade.trader_bot_id, trade.strategist_bot_id} - {None}:
        bot = db.get(TradingBot, bot_id)
        if bot:
            bot.trades += 1
            bot.wins += trade.pnl > 0
            bot.losses += trade.pnl <= 0
            bot.pnl += trade.pnl
    audit.record(db, actor_type="system", actor_id=ACTOR, action=f"trading.{trade.mode}.close",
                 target_type="trade", target_id=str(trade.id),
                 details={"symbol": trade.symbol, "exit": str(exit_price), "reason": reason,
                          "pnl": str(trade.pnl), "fees": str(fees)})  # fmt: skip
    events.emit(db, "trading.closed", trade_id=trade.id, symbol=trade.symbol, reason=reason,
                pnl=str(trade.pnl), mode=trade.mode)  # fmt: skip
    return trade


def exit_reason(
    trade: TradingTrade, candles: list[list[float]], acct: TradingAccount, now: datetime
) -> tuple[str, float] | None:
    """Whether an open trade must close now, and at what price. Stops are checked against every
    candle since entry, so a stop touched between checks still counts at the stop price."""
    opened = trade.opened_at if trade.opened_at.tzinfo else trade.opened_at.replace(tzinfo=UTC)
    stop, target = float(trade.stop_price), float(trade.target_price)
    long = trade.side == "long"
    for c in candles:
        if c[0] + 60 < opened.timestamp():
            continue
        if (long and c[3] <= stop) or (not long and c[2] >= stop):
            return "stop", stop
        if (long and c[2] >= target) or (not long and c[3] <= target):
            return "target", target
    last = float(candles[-1][4]) if candles else float(trade.last_price or trade.entry_price)
    if acct.kill_switch:
        return "kill_switch", last
    if acct.halted_reason:
        return "day_loss_limit", last
    if clock.must_square_off(trade.market, now):
        return "square_off", last
    return None


def record_curve(acct: TradingAccount, eq: Decimal, now: datetime) -> None:
    curve = list(acct.equity_curve or [])
    if curve and now.timestamp() - curve[-1]["t"] < CURVE_EVERY.total_seconds():
        curve[-1] = {"t": curve[-1]["t"], "equity": float(eq)}
    else:
        curve.append({"t": int(now.timestamp()), "equity": float(eq)})
    acct.equity_curve = curve[-600:]
    acct.peak_equity = max(acct.peak_equity, eq)


def instrument(symbol: str) -> Instrument:
    return BY_SYMBOL[symbol]
