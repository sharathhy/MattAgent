import json
import math
import random
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from urllib.parse import parse_qs

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.llm.router import ModelRouter
from app.models import AuditLog, TradingBot, TradingInsight, TradingTrade
from app.trading import backtest, clock, costs, desk, news, strategies, swarm
from app.trading import indicators as ind
from app.trading.broker import KiteBroker, KiteClient, PaperBroker
from app.trading.market import Candle, parse_binance, parse_yahoo
from app.trading.universe import BY_SYMBOL, Instrument

# Wednesday 10:30 IST: NSE entry window open.
NOW = datetime(2026, 10, 7, 5, 0, tzinfo=UTC)


def make_candles(
    n: int = 240, end: datetime = NOW, start: float = 100.0, seed: int = 1
) -> list[Candle]:
    rng = random.Random(seed)  # noqa: S311
    out: list[Candle] = []
    price = start
    t0 = end.timestamp() - n * 300
    for i in range(n):
        drift = math.sin(i / 9) * 0.6 + rng.uniform(-0.4, 0.4)
        o = price
        c = max(1.0, o + drift)
        out.append(
            [t0 + i * 300, o, max(o, c) + 0.3, min(o, c) - 0.3, c, 1000 + rng.random() * 500]
        )
        price = c
    return out


class FakeFeed:
    def __init__(self, candles: list[Candle] | None = None) -> None:
        self.data = candles or make_candles()
        self.calls: list[str] = []

    def candles(self, inst: Instrument, interval: str) -> list[Candle]:
        self.calls.append(f"{inst.symbol}:{interval}")
        return self.data


def router(settings: Settings) -> ModelRouter:
    return ModelRouter(settings, providers=[])


# --- Pure pieces -----------------------------------------------------------------------------


def test_indicators_and_patterns() -> None:
    closes = [float(x) for x in range(1, 60)]
    assert ind.ema(closes, 5)[-1] < closes[-1]
    assert ind.rsi(closes)[-1] > 90  # straight up
    c = make_candles(60)
    s = ind.summary(c)
    assert {"rsi", "vwap", "atr", "ema9", "trend", "macd"} <= s.keys()
    engulf = [[0, 10, 10.5, 9, 9.2, 1], [300, 9.1, 10.8, 9.0, 10.6, 1]]
    assert "bullish_engulfing" in ind.patterns(engulf)


def test_every_strategy_produces_signals_and_mutations_stay_in_range() -> None:
    c = make_candles(300)
    rng = random.Random(3)  # noqa: S311
    for name in strategies.STRATEGIES:
        p = strategies.random_params(name, rng)
        sig = strategies.signals(name, c, p)
        assert len(sig) == len(c) and set(sig) <= {-1, 0, 1}
        m = strategies.mutate(name, p, rng, scale=5)
        for key, (lo, hi, _) in strategies.space(name).items():
            assert lo <= m[key] <= hi


def test_backtest_deducts_costs_and_never_holds_overnight() -> None:
    c = make_candles(400)
    res = backtest.run(
        "ema_cross",
        c,
        {"fast": 5, "slow": 20, "stop_atr": 1.5, "rr": 2},
        cost_pct=costs.round_trip_pct("nse"),
    )
    assert res.trades > 0
    assert all(t["exit"] in {"stop", "target", "square_off", "end"} for t in res.log)
    free = backtest.run(
        "ema_cross", c, {"fast": 5, "slow": 20, "stop_atr": 1.5, "rr": 2}, cost_pct=0
    )
    assert free.return_pct > res.return_pct


def test_fitness_rewards_profit_not_win_rate() -> None:
    lucky = backtest.Result(trades=20, wins=18, losses=2, return_pct=-5.0, max_drawdown_pct=8)
    steady = backtest.Result(trades=20, wins=8, losses=12, return_pct=6.0, max_drawdown_pct=2)
    assert lucky.win_rate == 0.9 and steady.fitness > lucky.fitness


def test_costs_are_realistic() -> None:
    assert 0.0005 < costs.round_trip_pct("nse") < 0.0015
    assert costs.round_trip_pct("crypto") == pytest.approx(0.002)


def test_clock_intraday_rules() -> None:
    assert clock.can_enter("nse", NOW)
    assert not clock.can_enter("nse", NOW.replace(hour=9, minute=30))  # 15:00 IST
    assert clock.must_square_off("nse", NOW.replace(hour=9, minute=45))  # 15:15 IST
    assert clock.must_square_off("nse", datetime(2026, 10, 10, 5, 0, tzinfo=UTC))  # Saturday
    assert clock.must_square_off("crypto", NOW.replace(hour=18, minute=5))  # 23:35 IST


def test_feed_parsers() -> None:
    yahoo = {
        "chart": {
            "result": [
                {
                    "timestamp": [1, 2],
                    "indicators": {
                        "quote": [
                            {
                                "open": [1, None],
                                "high": [2, 2],
                                "low": [0.5, 1],
                                "close": [1.5, 1],
                                "volume": [10, 5],
                            }
                        ]
                    },
                }
            ]
        }
    }
    assert parse_yahoo(yahoo) == [[1.0, 1.0, 2.0, 0.5, 1.5, 10.0]]
    assert parse_binance([[1000, "1", "2", "0.5", "1.5", "7"]], 80) == [
        [1.0, 80.0, 160.0, 40.0, 120.0, 7.0]
    ]


def test_news_scoring_and_rss() -> None:
    assert news.score("Shares surge to record high on strong results") > 0
    assert news.score("Stock plunges after fraud probe") < 0
    xml = (
        "<rss><channel><item><title>SBIN shares jump on profit beat</title><link>https://x/1</link>"
        "<pubDate>Wed, 07 Oct 2026 04:00:00 GMT</pubDate></item></channel></rss>"
    )
    items = news.fetch(BY_SYMBOL["SBIN"], get=lambda url: xml)
    assert items[0].sentiment > 0 and items[0].published is not None
    assert news.parse("<not xml") == []


# --- Swarm and desk --------------------------------------------------------------------------


def test_swarm_has_300_bots(db: Session) -> None:
    assert swarm.ensure_bots(db) == 300
    assert swarm.ensure_bots(db) == 0
    counts = dict(db.execute(select(TradingBot.role, func.count()).group_by(TradingBot.role)).all())
    assert counts == swarm.ROLE_COUNTS


def test_tick_runs_bots_and_writes_snapshots(db: Session, settings: Settings) -> None:
    feed = FakeFeed()
    ran = swarm.tick(
        db, router(settings), feed, PaperBroker(), now=NOW, news_get=lambda u: "<rss/>"
    )
    assert ran == swarm.PER_TICK
    assert feed.calls  # analysts fetched candles
    research = db.scalar(select(TradingInsight).where(TradingInsight.kind == "research"))
    assert research is not None and "built-in notes" in (research.content or "")
    acct = desk.account(db)
    assert acct.last_tick_at is not None and acct.equity_curve


def _prime(db: Session, symbol: str, candles: list[Candle]) -> None:
    swarm.store_snapshot(db, BY_SYMBOL[symbol], "5m", candles, NOW)
    db.commit()


def _order(symbol: str, price: float, side: int = 1, atr: float = 1.0) -> desk.Order:
    return desk.Order(
        inst=BY_SYMBOL[symbol],
        side=side,
        price=price,
        atr=atr,
        params={"stop_atr": 1.5, "rr": 2},
        features={"bucket": "long|up|low|mid"},
        strategy="ema_cross",
        trader=None,
        strategist=None,
    )


def test_position_size_respects_risk_and_cash(db: Session) -> None:
    acct = desk.account(db)
    trade = desk.open_trade(db, acct, PaperBroker(), _order("YESBANK", 20.0), NOW)
    assert trade is not None
    risk = (trade.entry_price - trade.stop_price) * trade.qty
    assert risk <= Decimal("2.0") + Decimal("0.01")  # 2% of ₹100
    assert trade.qty == int(trade.qty)  # whole shares on NSE
    assert acct.cash >= 0
    # Same symbol twice is refused; unaffordable share prices are refused.
    assert desk.open_trade(db, acct, PaperBroker(), _order("YESBANK", 20.0), NOW) is None
    assert desk.open_trade(db, acct, PaperBroker(), _order("TCS", 4000.0), NOW) is None


def test_crypto_is_fractional_long_only(db: Session) -> None:
    acct = desk.account(db)
    assert (
        desk.open_trade(db, acct, PaperBroker(), _order("BTC", 5_000_000.0, side=-1), NOW) is None
    )
    t = desk.open_trade(db, acct, PaperBroker(), _order("BTC", 5_000_000.0, atr=20_000), NOW)
    assert t is not None and 0 < t.qty < 1


def test_stop_loss_closes_and_retrains(db: Session) -> None:
    swarm.ensure_bots(db)
    candles = make_candles(240, start=20)
    _prime(db, "YESBANK", candles)
    strat = db.scalar(
        select(TradingBot).where(TradingBot.role == "strategist", TradingBot.symbol == "YESBANK")
    )
    assert strat is not None
    acct = desk.account(db)
    price = candles[-1][4]
    order = desk.Order(
        inst=BY_SYMBOL["YESBANK"],
        side=1,
        price=price,
        atr=0.5,
        params={"stop_atr": 1.5, "rr": 2},
        features={"bucket": "long|down|high|mid"},
        strategy=strat.strategy,
        trader=None,
        strategist=strat,
    )
    trade = desk.open_trade(db, acct, PaperBroker(), order, NOW)
    assert trade is not None
    db.commit()
    crash = [*candles, [NOW.timestamp() + 60, price, price, price - 5, price - 5, 999]]
    later = NOW + timedelta(minutes=2)
    swarm.manage_positions(db, acct, FakeFeed(crash), PaperBroker(), later)
    db.refresh(trade)
    assert trade.status == "closed" and trade.exit_reason == "stop"
    assert trade.pnl < 0
    assert acct.cash < Decimal("100")
    lesson = db.scalar(select(TradingInsight).where(TradingInsight.kind == "lesson"))
    assert lesson is not None and "retrained" in lesson.title
    db.refresh(strat)
    assert strat.losses == 1 and strat.memory["conditions"]["long|down|high|mid"] == [0, 1]


def test_learned_avoid_list_after_repeated_losses() -> None:
    bot = TradingBot(slug="x", name="x", role="trader", memory={})
    swarm._remember(bot, "long|down|high|low", False)
    assert swarm._remember(bot, "long|down|high|low", False) == ["long|down|high|low"]


def test_day_loss_limit_halts_and_squares_off(db: Session) -> None:
    acct = desk.account(db)
    candles = make_candles(240, start=20)
    _prime(db, "YESBANK", candles)
    trade = desk.open_trade(
        db, acct, PaperBroker(), _order("YESBANK", candles[-1][4], atr=0.2), NOW
    )
    assert trade is not None
    acct.day = clock.trading_day(NOW)
    acct.day_start_equity = Decimal("200")  # pretend we started the day far higher
    db.commit()
    swarm.manage_positions(db, acct, FakeFeed(candles), PaperBroker(), NOW)
    db.refresh(trade)
    assert acct.halted_reason and "Daily loss limit" in acct.halted_reason
    assert trade.status == "closed" and trade.exit_reason == "day_loss_limit"
    assert desk.open_trade(db, acct, PaperBroker(), _order("SUZLON", 50.0), NOW) is None
    # The halt lifts on the next trading day.
    desk.roll_day(db, acct, NOW + timedelta(days=1))
    assert acct.halted_reason is None


def test_square_off_before_close(db: Session) -> None:
    acct = desk.account(db)
    candles = make_candles(240, start=20)
    _prime(db, "YESBANK", candles)
    trade = desk.open_trade(
        db, acct, PaperBroker(), _order("YESBANK", candles[-1][4], atr=0.2), NOW
    )
    assert trade is not None
    db.commit()
    late = NOW.replace(hour=9, minute=45)  # 15:15 IST
    flat = [[late.timestamp() - 60, *[candles[-1][4]] * 4, 10]]
    swarm.manage_positions(db, acct, FakeFeed([*candles, flat[0]]), PaperBroker(), late)
    db.refresh(trade)
    assert trade.exit_reason == "square_off"


def test_live_trade_is_not_closed_without_a_broker_session(db: Session) -> None:
    acct = desk.account(db)
    t = TradingTrade(
        mode="live",
        symbol="SBIN",
        market="nse",
        side="long",
        qty=Decimal(1),
        entry_price=Decimal(800),
        stop_price=Decimal(790),
        target_price=Decimal(820),
        status="open",
        opened_at=NOW,
        pnl=Decimal(0),
        fees=Decimal(0),
    )
    db.add(t)
    db.commit()
    desk.close_trade(db, acct, PaperBroker(), t, 805, "square_off", NOW)
    assert t.status == "open"


# --- Kite (live broker) ----------------------------------------------------------------------


def kite_transport(log: list[tuple[str, str, dict[str, Any]]]) -> httpx.MockTransport:
    def handler(req: httpx.Request) -> httpx.Response:
        form = {k: v[0] for k, v in parse_qs(req.content.decode()).items()}
        log.append((req.method, req.url.path, form))
        if req.url.path == "/session/token":
            return httpx.Response(200, json={"status": "success", "data": {"access_token": "tok"}})
        if req.url.path == "/user/margins/equity":
            return httpx.Response(
                200, json={"status": "success", "data": {"available": {"live_balance": 5000}}}
            )
        if req.url.path == "/orders/regular" and req.method == "POST":
            return httpx.Response(
                200, json={"status": "success", "data": {"order_id": str(len(log))}}
            )
        if req.url.path.startswith("/orders/regular/"):
            return httpx.Response(200, json={"status": "success", "data": {"order_id": "x"}})
        if req.url.path.startswith("/orders/"):
            return httpx.Response(
                200,
                json={
                    "status": "success",
                    "data": [{"status": "COMPLETE", "average_price": 801.5}],
                },
            )
        return httpx.Response(404, json={"status": "error", "message": "nope"})

    return httpx.MockTransport(handler)


def test_kite_orders_are_intraday_with_a_protective_stop() -> None:
    log: list[tuple[str, str, dict[str, Any]]] = []
    client = KiteClient(
        "key",
        "tok",
        http=httpx.Client(base_url="https://api.kite.trade", transport=kite_transport(log)),
    )
    broker = KiteBroker(client)
    orders = broker.enter("SBIN", "long", 3, 790.12)
    posts = [f for m, p, f in log if m == "POST"]
    assert posts[0]["transaction_type"] == "BUY" and posts[0]["product"] == "MIS"
    assert posts[1]["order_type"] == "SL-M" and posts[1]["trigger_price"] == "790.10"
    assert orders["fill_price"] == 801.5
    broker.exit("SBIN", "long", 3, orders)
    assert any(m == "DELETE" for m, _, _ in log)
    assert [f["transaction_type"] for m, p, f in log if m == "POST"][-1] == "SELL"
    assert not any("withdraw" in p or "fund" in p for _, p, _ in log)


def test_kite_session_checksum() -> None:
    log: list[tuple[str, str, dict[str, Any]]] = []
    client = KiteClient(
        "key", http=httpx.Client(base_url="https://api.kite.trade", transport=kite_transport(log))
    )
    assert client.create_session("req", "secret") == "tok"
    import hashlib

    assert log[0][2]["checksum"] == hashlib.sha256(b"keyreqsecret").hexdigest()


# --- API -------------------------------------------------------------------------------------


def test_overview_api(client: TestClient, owner_headers: dict[str, str]) -> None:
    r = client.get("/api/trading", headers=owner_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["account"]["mode"] == "paper" and body["account"]["equity"] == 100
    assert sum(x["bots"] for x in body["roles"]) == 300
    assert body["account"]["doublings_to_goal"] == pytest.approx(23.3, abs=0.1)


def test_kill_switch_and_owner_only_controls(
    client: TestClient, owner_headers: dict[str, str], viewer_headers: dict[str, str]
) -> None:
    assert client.post("/api/trading/stop", headers=viewer_headers).status_code == 403
    r = client.post("/api/trading/stop", headers=owner_headers)
    assert r.json()["kill_switch"] is True and r.json()["blocked"] == "Kill switch is on"
    assert client.post("/api/trading/resume", headers=owner_headers).json()["kill_switch"] is False
    bad = client.patch(
        "/api/trading/settings", json={"max_day_loss_pct": 35}, headers=owner_headers
    )
    assert bad.status_code == 422
    ok = client.patch(
        "/api/trading/settings", json={"max_trade_risk_pct": 1.5}, headers=owner_headers
    )
    assert ok.json()["max_trade_risk_pct"] == 1.5


def test_voice_stop_trading(client: TestClient, owner_headers: dict[str, str]) -> None:
    r = client.post("/api/command", json={"text": "Matt, stop trading now"}, headers=owner_headers)
    assert r.status_code == 200 and r.json()["intent"] == "trading_stop"
    assert (
        client.get("/api/trading", headers=owner_headers).json()["account"]["kill_switch"] is True
    )


def test_demat_keys_are_encrypted_and_live_needs_login_and_phrase(
    client: TestClient, owner_headers: dict[str, str], db: Session
) -> None:
    body = {
        "label": "Zerodha",
        "client_id": "ab1234",
        "api_key": "kitekey123",
        "api_secret": "kitesecret99",
    }
    r = client.post("/api/trading/brokers", json=body, headers=owner_headers)
    assert r.status_code == 201
    assert "kitekey123" not in json.dumps(r.json()) and r.json()["status"] == "needs_login"
    url = client.get(f"/api/trading/brokers/{r.json()['id']}/login", headers=owner_headers).json()[
        "url"
    ]
    assert "api_key=kitekey123" in url
    live = {"confirm": "yes", "capital_cap_inr": 500}
    refused = client.post("/api/trading/live", json=live, headers=owner_headers)
    assert refused.status_code == 400 and "Type exactly" in refused.json()["detail"]
    live["confirm"] = "I understand MATT can lose my real money"
    refused = client.post("/api/trading/live", json=live, headers=owner_headers)
    assert refused.status_code == 400 and "login" in refused.json()["detail"]
    assert (
        db.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.action == "trading.broker_added")
        )
        == 1
    )
