"""Trading tables: the account, the 300-bot swarm, market snapshots, trades, insights, brokers.

Paper trading is the default. Real orders only ever go to the owner's own demat account through
a broker API, and only after the owner connects a broker and confirms Live mode in words.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, utcnow

MONEY = Numeric(18, 4)
QTY = Numeric(24, 8)


class TradingAccount(TimestampMixin, Base):
    """Single row: the trading desk's settings, balance and hard limits."""

    __tablename__ = "trading_account"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    mode: Mapped[str] = mapped_column(String(10), default="paper")  # paper | live
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    #: Owner's kill switch: when set, nothing opens and everything open is squared off.
    kill_switch: Mapped[bool] = mapped_column(Boolean, default=False)
    starting_capital: Mapped[Decimal] = mapped_column(MONEY)
    cash: Mapped[Decimal] = mapped_column(MONEY)
    realized_pnl: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    fees_paid: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    peak_equity: Mapped[Decimal] = mapped_column(MONEY)
    day: Mapped[str | None] = mapped_column(String(10))
    day_start_equity: Mapped[Decimal] = mapped_column(MONEY)
    goal_inr: Mapped[Decimal] = mapped_column(Numeric(20, 2))
    max_trade_risk_pct: Mapped[float] = mapped_column(Float, default=2.0)
    max_day_loss_pct: Mapped[float] = mapped_column(Float, default=20.0)
    max_open_positions: Mapped[int] = mapped_column(Integer, default=3)
    #: Live mode only: the most of the owner's real money MATT may put at risk at once.
    live_capital_cap_inr: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    live_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    live_confirmed_by: Mapped[str | None] = mapped_column(String(100))
    halted_reason: Mapped[str | None] = mapped_column(String(300))
    halted_day: Mapped[str | None] = mapped_column(String(10))
    bot_cursor: Mapped[int] = mapped_column(Integer, default=0)
    last_tick_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    equity_curve: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)


class TradingBot(TimestampMixin, Base):
    """One logical bot. Roles: research, news, analyst, strategist, trader."""

    __tablename__ = "trading_bots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(20), index=True)
    symbol: Mapped[str | None] = mapped_column(String(30), index=True)
    interval: Mapped[str | None] = mapped_column(String(10))
    strategy: Mapped[str | None] = mapped_column(String(50))
    topic: Mapped[str | None] = mapped_column(String(300))
    params: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    memory: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    generation: Mapped[int] = mapped_column(Integer, default=1)
    runs: Mapped[int] = mapped_column(Integer, default=0)
    trades: Mapped[int] = mapped_column(Integer, default=0)
    wins: Mapped[int] = mapped_column(Integer, default=0)
    losses: Mapped[int] = mapped_column(Integer, default=0)
    pnl: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    fitness: Mapped[float] = mapped_column(Float, default=0.0)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_note: Mapped[str | None] = mapped_column(Text)


class MarketSnapshot(Base):
    """Latest candles and indicators for one symbol and candle size, written by analyst bots."""

    __tablename__ = "market_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(50), unique=True, index=True)  # SYMBOL:interval
    symbol: Mapped[str] = mapped_column(String(30), index=True)
    market: Mapped[str] = mapped_column(String(10))
    interval: Mapped[str] = mapped_column(String(10))
    price_inr: Mapped[Decimal] = mapped_column(MONEY)
    change_pct: Mapped[float] = mapped_column(Float, default=0.0)
    candles: Mapped[list[list[float]]] = mapped_column(JSON, default=list)
    indicators: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    patterns: Mapped[list[str]] = mapped_column(JSON, default=list)
    last_candle_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TradingTrade(TimestampMixin, Base):
    __tablename__ = "trading_trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    mode: Mapped[str] = mapped_column(String(10), index=True)  # paper | live
    symbol: Mapped[str] = mapped_column(String(30), index=True)
    market: Mapped[str] = mapped_column(String(10))
    side: Mapped[str] = mapped_column(String(5))  # long | short
    qty: Mapped[Decimal] = mapped_column(QTY)
    entry_price: Mapped[Decimal] = mapped_column(MONEY)
    stop_price: Mapped[Decimal] = mapped_column(MONEY)
    target_price: Mapped[Decimal] = mapped_column(MONEY)
    exit_price: Mapped[Decimal | None] = mapped_column(MONEY)
    last_price: Mapped[Decimal | None] = mapped_column(MONEY)
    status: Mapped[str] = mapped_column(String(10), index=True)  # open | closed
    exit_reason: Mapped[str | None] = mapped_column(String(50))
    pnl: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    fees: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    trader_bot_id: Mapped[int | None] = mapped_column(ForeignKey("trading_bots.id"), index=True)
    strategist_bot_id: Mapped[int | None] = mapped_column(ForeignKey("trading_bots.id"))
    strategy: Mapped[str | None] = mapped_column(String(50))
    features: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    broker_orders: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TradingInsight(Base):
    """What research, news and retraining bots learned: notes, scored headlines, lessons."""

    __tablename__ = "trading_insights"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(20), index=True)  # research | news | lesson
    symbol: Mapped[str | None] = mapped_column(String(30), index=True)
    title: Mapped[str] = mapped_column(String(500))
    url: Mapped[str | None] = mapped_column(String(1000))
    sentiment: Mapped[float | None] = mapped_column(Float)
    content: Mapped[str | None] = mapped_column(Text)
    bot_id: Mapped[int | None] = mapped_column(ForeignKey("trading_bots.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )


class BrokerAccount(TimestampMixin, Base):
    """The owner's demat/broker connection. Keys are encrypted at rest and never shown again."""

    __tablename__ = "broker_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    broker: Mapped[str] = mapped_column(String(20))  # zerodha
    label: Mapped[str] = mapped_column(String(100))
    client_id: Mapped[str] = mapped_column(String(50))
    api_key_enc: Mapped[str] = mapped_column(Text)
    api_secret_enc: Mapped[str] = mapped_column(Text)
    access_token_enc: Mapped[str | None] = mapped_column(Text)
    token_day: Mapped[str | None] = mapped_column(String(10))
    funds_inr: Mapped[Decimal | None] = mapped_column(MONEY)
    status: Mapped[str] = mapped_column(String(20), default="needs_login")
    last_error: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(100))
