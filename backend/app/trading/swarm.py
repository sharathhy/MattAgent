"""The 300-bot trading swarm.

"300 bots" are 300 logical bots: rows with their own role, assignment, parameters, memory and
track record, run in turns by the background worker inside one free Render server. Each tick runs
a handful of them, so every bot gets a turn every few minutes without hitting free-tier limits.

Roles (counts add up to 300):
- 30 research bots study one intraday topic each, using a free AI model when one is connected;
- 30 news bots score free headlines for one symbol each;
- 60 analyst bots fetch candles for one symbol and candle size and compute indicators/patterns;
- 120 strategist bots each own one strategy on one symbol, backtest it, evolve its parameters,
  and retrain when a live (paper or real) trade it signalled loses;
- 60 trader bots combine strategist votes, news and learned "avoid" conditions and place trades
  through the desk, which enforces every hard limit.
"""

import random
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.llm.router import ModelRouter, NoModelAvailable
from app.models import MarketSnapshot, TradingAccount, TradingBot, TradingInsight, TradingTrade
from app.services import events
from app.trading import backtest, clock, costs, desk, news, strategies
from app.trading import indicators as ind
from app.trading.broker import Broker
from app.trading.market import Candle, Feed
from app.trading.universe import BY_SYMBOL, INSTRUMENTS, INTERVALS, Instrument

ROLE_COUNTS = {"research": 30, "news": 30, "analyst": 60, "strategist": 120, "trader": 60}
#: Bots run per worker tick, by role (least recently run first).
PER_TICK = {"analyst": 4, "strategist": 6, "trader": 4, "news": 1, "research": 1}
RESEARCH_EVERY = timedelta(hours=24)
NEWS_EVERY = timedelta(minutes=30)
SIGNAL_TTL = timedelta(minutes=20)
FRESH_DATA = timedelta(minutes=25)
INTERVAL_SECONDS = {"5m": 300, "15m": 900}
TRADER_STYLES = {"steady": 0.5, "bold": 0.3}
STRATEGIST_INTERVAL = "5m"

RESEARCH_TOPICS: dict[str, str] = {
    "VWAP as an intraday bias": "Price above VWAP favours longs, below favours shorts; institutions benchmark fills to VWAP, so first touches often act as support or resistance.",
    "Opening range breakout": "The first 15-30 minutes set a range; breakouts with volume tend to follow through, but false breaks are common on low-volume days.",
    "Position sizing and the 1-2% rule": "Size every trade so the stop costs a fixed small slice of capital; this, not win rate, is what keeps an account alive.",
    "Stop-loss placement with ATR": "Stops of 1-2x ATR sit outside normal noise; tighter stops get hit by random movement more often than they save.",
    "Risk-reward and expectancy": "Expectancy = win rate x average win - loss rate x average loss. A 40% win rate with 2:1 reward is profitable; a 90% win rate with tiny wins and big losses is not.",
    "Candlestick reversal patterns": "Hammers, engulfing candles and dojis matter mostly at support/resistance and in the direction of the higher-timeframe trend; alone they are weak.",
    "Trend filters with EMAs": "Trading only in the direction of the 50-period EMA removes many losing counter-trend trades.",
    "RSI in trending vs ranging markets": "RSI oversold buys work in ranges and fail in strong downtrends, where RSI can stay low for long.",
    "Volume confirmation": "Breakouts on above-average volume are more reliable; breakouts on thin volume often reverse.",
    "NSE market timings and square-off": "NSE cash trades 09:15-15:30 IST; brokers auto-square MIS positions around 15:20 with a fee, so exit earlier.",
    "Intraday costs in India": "STT, exchange fees, GST and stamp duty make very small, frequent trades unprofitable; each trade must move more than costs.",
    "Avoiding the first five minutes": "The open is volatile with wide spreads; many intraday traders wait for the first candles to settle.",
    "News-driven moves": "Results, block deals and regulatory news cause gaps; trading against fresh news is risky.",
    "Bollinger Band squeeze": "Low band width often precedes a volatility expansion; direction is unknown until the break.",
    "MACD momentum": "MACD crosses on the same side of zero confirm momentum; crosses near zero in ranges whipsaw.",
    "Overtrading and revenge trading": "Losses invite bigger, worse trades; a daily loss limit stops the spiral.",
    "Liquidity and slippage": "Thinly traded stocks fill worse than the chart shows; prefer liquid names.",
    "Crypto intraday sessions": "Crypto trades 24/7 with volume peaks when US and Europe overlap; weekends are thinner.",
    "Bitcoin dominance and altcoins": "Altcoins usually follow Bitcoin's direction with larger swings.",
    "Support and resistance levels": "Previous day high/low and round numbers attract orders and reactions.",
    "Gap-up and gap-down days": "Large gaps often partly fill intraday; chasing a gap at the open is risky.",
    "Backtesting pitfalls": "Overfitting to recent candles, ignoring costs and look-ahead bias make backtests look better than live results.",
    "Market regime detection": "Strategies that work in trends fail in ranges and vice versa; measure the regime first.",
    "Pre-market and global cues": "SGX/GIFT Nifty, US futures and crude oil set the opening tone for Indian markets.",
    "Sector rotation intraday": "Money moves between sectors through the day; leaders often keep leading.",
    "Short selling intraday in India": "Cash-market shorts must be closed the same day; you cannot carry them overnight.",
    "Trailing stops": "Moving the stop behind price locks in gains but can cut winners early in choppy markets.",
    "Psychology and discipline": "Following the plan matters more than any single signal; record every trade.",
    "Indian crypto taxation": "India taxes crypto gains at 30% and withholds 1% TDS on sales; losses can't offset other income.",
    "Why 90% win rates are a red flag": "Very high win rates usually mean small targets and large stops; a few losses erase many wins.",
}  # fmt: skip
RESEARCH_SYSTEM = (
    "You are a careful intraday trading researcher. Give practical, evidence-based rules for NSE "
    "cash-market and spot-crypto intraday trading. No futures or options. Be honest about what "
    "doesn't work and about risk. Under 180 words, plain text."
)


# --- Setup ---------------------------------------------------------------------------------


def ensure_bots(db: Session) -> int:
    """Create the 300 bots once. Idempotent."""
    existing = int(db.scalar(select(func.count()).select_from(TradingBot)) or 0)
    if existing >= sum(ROLE_COUNTS.values()):
        return 0
    have = set(db.scalars(select(TradingBot.slug)).all())
    rng = random.Random(42)
    names = list(strategies.STRATEGIES)
    rows: list[TradingBot] = []

    def add(slug: str, **kw: Any) -> None:
        if slug not in have:
            rows.append(TradingBot(slug=slug, params=kw.pop("params", {}), memory={}, **kw))

    for i, topic in enumerate(RESEARCH_TOPICS):
        add(f"research-{i + 1:02d}", name=f"Researcher {i + 1}: {topic}", role="research", topic=topic)
    for inst in INSTRUMENTS:
        add(f"news-{inst.symbol.lower()}", name=f"News scout: {inst.symbol}", role="news",
            symbol=inst.symbol)  # fmt: skip
        for interval in INTERVALS:
            add(f"analyst-{inst.symbol.lower()}-{interval}",
                name=f"Chart analyst: {inst.symbol} {interval}", role="analyst",
                symbol=inst.symbol, interval=interval)  # fmt: skip
    for k, inst in enumerate(INSTRUMENTS):
        for j in range(4):
            name = names[(k + 2 * j) % len(names)]
            add(f"strategist-{inst.symbol.lower()}-{name}",
                name=f"Strategist: {name.replace('_', ' ')} on {inst.symbol}", role="strategist",
                symbol=inst.symbol, interval=STRATEGIST_INTERVAL, strategy=name,
                params=strategies.random_params(name, rng))  # fmt: skip
        for style in TRADER_STYLES:
            add(f"trader-{inst.symbol.lower()}-{style}", name=f"Trader ({style}): {inst.symbol}",
                role="trader", symbol=inst.symbol, params={"style": style})  # fmt: skip
    db.add_all(rows)
    db.commit()
    return len(rows)


# --- Tick ----------------------------------------------------------------------------------


def due_bots(db: Session, role: str, n: int) -> list[TradingBot]:
    stmt = (
        select(TradingBot).where(TradingBot.role == role)
        .order_by(TradingBot.last_run_at.asc().nulls_first(), TradingBot.id).limit(n)
    )  # fmt: skip
    return list(db.scalars(stmt).all())


def tick(
    db: Session, router: ModelRouter, feed: Feed, broker: Broker, *,
    now: datetime | None = None, news_get: Any = None,
) -> dict[str, int]:  # fmt: skip
    """One heartbeat: guard open positions, then give a few bots of each role their turn."""
    now = now or datetime.now(UTC)
    ensure_bots(db)
    acct = desk.account(db)
    acct.last_tick_at = now
    desk.roll_day(db, acct, now)
    manage_positions(db, acct, feed, broker, now)
    ran: dict[str, int] = {}
    for role, n in PER_TICK.items():
        ran[role] = 0
        for bot in due_bots(db, role, n):
            try:
                RUNNERS[role](db, bot, acct=acct, router=router, feed=feed, broker=broker,
                              now=now, news_get=news_get)  # fmt: skip
            except Exception as exc:  # one bot failing must not stop the swarm
                bot.last_note = f"Error: {str(exc)[:300]}"
            bot.runs += 1
            bot.last_run_at = now
            ran[role] += 1
        db.commit()
    desk.record_curve(acct, desk.equity(db, acct), now)
    db.commit()
    return ran


def manage_positions(db: Session, acct: TradingAccount, feed: Feed, broker: Broker, now: datetime) -> None:
    trades = desk.open_trades(db)
    for trade in trades:
        inst = BY_SYMBOL[trade.symbol]
        candles = feed.candles(inst, "5m") or snapshot_candles(db, trade.symbol, "5m")
        if candles:
            store_snapshot(db, inst, "5m", candles, now)
            trade.last_price = Decimal(str(round(candles[-1][4], 4)))
    eq = desk.equity(db, acct)
    desk.check_day_loss(db, acct, eq)
    for trade in trades:
        candles = snapshot_candles(db, trade.symbol, "5m")
        hit = desk.exit_reason(trade, candles, acct, now)
        if hit:
            closed = desk.close_trade(db, acct, broker, trade, hit[1], hit[0], now)
            if closed.status == "closed":
                learn(db, closed)
    db.commit()


# --- Snapshots -----------------------------------------------------------------------------


def snapshot(db: Session, symbol: str, interval: str) -> MarketSnapshot | None:
    return db.scalar(select(MarketSnapshot).where(MarketSnapshot.key == f"{symbol}:{interval}"))


def snapshot_candles(db: Session, symbol: str, interval: str) -> list[Candle]:
    snap = snapshot(db, symbol, interval)
    return list(snap.candles) if snap else []


def store_snapshot(db: Session, inst: Instrument, interval: str, candles: list[Candle], now: datetime) -> MarketSnapshot:
    snap = snapshot(db, inst.symbol, interval)
    if snap is None:
        snap = MarketSnapshot(key=f"{inst.symbol}:{interval}", symbol=inst.symbol, market=inst.market,
                              interval=interval, price_inr=Decimal("0"))  # fmt: skip
        db.add(snap)
    candles = candles[-300:]
    last = candles[-1]
    day = int(last[0] // 86400)
    first_today = next((c for c in candles if int(c[0] // 86400) == day), last)
    snap.candles = [[round(v, 6) for v in c] for c in candles]
    snap.price_inr = Decimal(str(round(last[4], 4)))
    snap.change_pct = round((last[4] - first_today[1]) / first_today[1] * 100, 3) if first_today[1] else 0
    snap.indicators = {k: (round(v, 4) if isinstance(v, float) else v)
                       for k, v in ind.summary(candles).items()}  # fmt: skip
    snap.patterns = ind.patterns(candles)
    snap.last_candle_at = datetime.fromtimestamp(last[0], UTC)
    snap.updated_at = now
    return snap


def closed_candles(candles: list[Candle], interval: str, now: datetime) -> list[Candle]:
    """Drop the still-forming candle so signals don't repaint."""
    if candles and candles[-1][0] + INTERVAL_SECONDS.get(interval, 300) > now.timestamp():
        return candles[:-1]
    return candles


def fresh(candles: list[Candle], now: datetime) -> bool:
    return bool(candles) and now.timestamp() - candles[-1][0] <= FRESH_DATA.total_seconds()


# --- Role runners --------------------------------------------------------------------------


def run_analyst(db: Session, bot: TradingBot, *, feed: Feed, now: datetime, **_: Any) -> None:
    inst = BY_SYMBOL[bot.symbol or ""]
    candles = feed.candles(inst, bot.interval or "5m")
    if not candles:
        bot.last_note = "No market data from the free feed this turn."
        return
    snap = store_snapshot(db, inst, bot.interval or "5m", candles, now)
    i = snap.indicators
    pats = f"; pattern: {', '.join(snap.patterns)}" if snap.patterns else ""
    bot.last_note = (f"₹{snap.price_inr} ({snap.change_pct:+.2f}% today), trend {i.get('trend')}, "
                     f"RSI {i.get('rsi', 0):.0f}, {'above' if i.get('price', 0) > i.get('vwap', 0) else 'below'} VWAP{pats}")  # fmt: skip


def run_news(db: Session, bot: TradingBot, *, now: datetime, news_get: Any = None, **_: Any) -> None:
    last = bot.memory.get("fetched_at")
    if last and now.timestamp() - float(last) < NEWS_EVERY.total_seconds():
        return
    inst = BY_SYMBOL[bot.symbol or ""]
    headlines = news.fetch(inst, news_get)
    seen = set(db.scalars(select(TradingInsight.title).where(
        TradingInsight.kind == "news", TradingInsight.symbol == inst.symbol)).all())  # fmt: skip
    added = 0
    for h in headlines:
        if h.title in seen:
            continue
        db.add(TradingInsight(kind="news", symbol=inst.symbol, title=h.title, url=h.url or None,
                              sentiment=h.sentiment, bot_id=bot.id,
                              created_at=h.published or now))  # fmt: skip
        added += 1
    bot.memory = {**bot.memory, "fetched_at": now.timestamp()}
    mood = sentiment(db, inst.symbol, now)
    bot.last_note = f"{added} new headline(s); news mood {mood:+.2f}" if headlines else "No headlines found this turn."


def run_research(db: Session, bot: TradingBot, *, router: ModelRouter, now: datetime, **_: Any) -> None:
    last = bot.memory.get("researched_at")
    if last and now.timestamp() - float(last) < RESEARCH_EVERY.total_seconds():
        return
    topic = bot.topic or ""
    content, source = RESEARCH_TOPICS.get(topic, ""), "MATT's built-in notes"
    if router.available:
        try:
            done = router.complete(db, system=RESEARCH_SYSTEM, prompt=f"Topic: {topic}", max_tokens=500)
            content, source = done.completion.text.strip(), f"free model {done.spec.model}"
        except NoModelAvailable:
            pass
    db.add(TradingInsight(kind="research", title=topic, content=f"{content}\n\nSource: {source}",
                          bot_id=bot.id, created_at=now))  # fmt: skip
    bot.memory = {**bot.memory, "researched_at": now.timestamp()}
    bot.last_note = f"Researched “{topic}” ({source})."


def run_strategist(db: Session, bot: TradingBot, *, now: datetime, **_: Any) -> None:
    inst = BY_SYMBOL[bot.symbol or ""]
    candles = closed_candles(snapshot_candles(db, inst.symbol, bot.interval or "5m"), bot.interval or "5m", now)
    if len(candles) < 60:
        bot.last_note = "Waiting for the chart analyst to collect enough candles."
        return
    name = bot.strategy or "ema_cross"
    avoid = list(bot.memory.get("avoid", []))
    kw = {"cost_pct": costs.round_trip_pct(inst.market), "allow_short": inst.market == "nse", "avoid": avoid}
    current = backtest.run(name, candles, bot.params, **kw)
    # Keep evolving: try one mutation every turn and keep it only if it backtests better.
    rng = random.Random(f"{bot.slug}:{bot.runs}")
    trial = strategies.mutate(name, bot.params, rng, scale=0.15)
    tried = backtest.run(name, candles, trial, **kw)
    if tried.fitness > current.fitness:
        bot.params, current = trial, tried
        bot.generation += 1
    bot.fitness = current.fitness
    sig = strategies.signals(name, candles, bot.params)[-1]
    if sig < 0 and inst.market != "nse":
        sig = 0
    feats = backtest.feature_series(candles)[-1]
    if sig and backtest.bucket(sig, feats) in avoid:
        sig = 0  # a condition this bot has learned loses money
    bot.memory = {**bot.memory, "backtest": current.as_dict(),
                  "signal": {"side": sig, "at": now.timestamp(), "candle": candles[-1][0]}}  # fmt: skip
    verdict = {1: "BUY signal", -1: "SELL signal", 0: "no signal"}[sig]
    bot.last_note = (f"Gen {bot.generation}: backtest {current.trades} trades, win rate "
                     f"{current.win_rate:.0%}, net {current.return_pct:+.2f}% after costs; {verdict}.")  # fmt: skip


def sentiment(db: Session, symbol: str, now: datetime) -> float:
    since = now - timedelta(hours=12)
    rows = db.scalars(select(TradingInsight.sentiment).where(
        TradingInsight.kind == "news", TradingInsight.symbol == symbol,
        TradingInsight.created_at >= since, TradingInsight.sentiment.is_not(None))).all()  # fmt: skip
    vals = [float(v) for v in rows if v is not None]
    return round(sum(vals) / len(vals), 3) if vals else 0.0


def consensus(db: Session, symbol: str, now: datetime) -> tuple[float, TradingBot | None]:
    """Fitness-weighted vote of this symbol's profitable strategists, and the best one voting."""
    bots = db.scalars(select(TradingBot).where(
        TradingBot.role == "strategist", TradingBot.symbol == symbol, TradingBot.fitness > 0)).all()  # fmt: skip
    total = vote = 0.0
    best: TradingBot | None = None
    for b in bots:
        s = b.memory.get("signal") or {}
        side = int(s.get("side", 0)) if now.timestamp() - float(s.get("at", 0)) <= SIGNAL_TTL.total_seconds() else 0
        total += b.fitness
        vote += side * b.fitness
        if side and (best is None or b.fitness > best.fitness):
            best = b
    return (vote / total if total else 0.0), best


def run_trader(
    db: Session, bot: TradingBot, *, acct: TradingAccount, broker: Broker, now: datetime, **_: Any
) -> None:
    inst = BY_SYMBOL[bot.symbol or ""]
    if why := desk.blocked(acct):
        bot.last_note = f"Standing by: {why}."
        return
    if not clock.can_enter(inst.market, now):
        bot.last_note = "Outside the entry window; no new trades."
        return
    candles = closed_candles(snapshot_candles(db, inst.symbol, "5m"), "5m", now)
    if not fresh(candles, now) or len(candles) < 60:
        bot.last_note = "No fresh market data, so no trade (stale data is treated as market closed)."
        return
    score, best = consensus(db, inst.symbol, now)
    mood = sentiment(db, inst.symbol, now)
    score += 0.15 * mood
    threshold = TRADER_STYLES.get(str(bot.params.get("style")), 0.5)
    side = 1 if score >= threshold else -1 if score <= -threshold else 0
    if not side or best is None:
        bot.last_note = f"No edge: strategist consensus {score:+.2f}, news {mood:+.2f}."
        return
    feats = backtest.feature_series(candles)[-1]
    cond = backtest.bucket(side, feats)
    if cond in bot.memory.get("avoid", []):
        bot.last_note = f"Skipped a {cond} setup: it has lost money for me before."
        return
    order = desk.Order(
        inst=inst, side=side, price=candles[-1][4], atr=ind.atr(candles)[-1], params=best.params,
        features={**feats, "bucket": cond, "consensus": round(score, 3), "news": mood},
        strategy=best.strategy, trader=bot, strategist=best,
    )  # fmt: skip
    trade = desk.open_trade(db, acct, broker, order, now)
    if trade is None:
        bot.last_note = f"Wanted to {'buy' if side > 0 else 'short'} but the desk's limits said no (position size, open slots or cash)."
        return
    bot.last_note = (f"{'Bought' if side > 0 else 'Shorted'} {trade.qty} {inst.symbol} at ₹{trade.entry_price} "
                     f"(stop ₹{trade.stop_price}, target ₹{trade.target_price}) on {best.strategy}.")  # fmt: skip


RUNNERS = {"analyst": run_analyst, "news": run_news, "research": run_research,
           "strategist": run_strategist, "trader": run_trader}  # fmt: skip


# --- Learning from results -----------------------------------------------------------------


def _remember(bot: TradingBot, cond: str, won: bool) -> list[str]:
    stats = dict(bot.memory.get("conditions", {}))
    w, lo = stats.get(cond, [0, 0])
    stats[cond] = [w + won, lo + (not won)]
    avoid = set(bot.memory.get("avoid", []))
    w, lo = stats[cond]
    if lo >= 2 and lo / (w + lo) >= 0.7:
        avoid.add(cond)
    bot.memory = {**bot.memory, "conditions": stats, "avoid": sorted(avoid)}
    return sorted(avoid)


def learn(db: Session, trade: TradingTrade) -> None:
    """After every closed trade: remember the market condition's outcome; after a loss, retrain
    the strategist that signalled it and write down the lesson."""
    won = trade.pnl > 0
    cond = str((trade.features or {}).get("bucket", ""))
    trader = db.get(TradingBot, trade.trader_bot_id) if trade.trader_bot_id else None
    strat = db.get(TradingBot, trade.strategist_bot_id) if trade.strategist_bot_id else None
    for bot in (trader, strat):
        if bot and cond:
            _remember(bot, cond, won)
    if won or strat is None:
        return
    lesson = retrain(db, strat)
    db.add(TradingInsight(
        kind="lesson", symbol=trade.symbol,
        title=f"Lost ₹{-trade.pnl:.2f} on {trade.symbol} ({trade.exit_reason}); {strat.name} retrained",
        content=f"Condition: {cond or 'unknown'}. {lesson}", bot_id=strat.id,
    ))  # fmt: skip
    events.emit(db, "trading.retrained", bot=strat.slug, lesson=lesson[:300])


def retrain(db: Session, bot: TradingBot) -> str:
    """Search nearby parameters (with the learned avoid list) and keep the best backtest."""
    inst = BY_SYMBOL[bot.symbol or ""]
    candles = snapshot_candles(db, inst.symbol, bot.interval or "5m")
    name = bot.strategy or "ema_cross"
    if len(candles) < 60:
        return "Not enough candles to retrain yet; the loss is remembered."
    kw = {"cost_pct": costs.round_trip_pct(inst.market), "allow_short": inst.market == "nse",
          "avoid": list(bot.memory.get("avoid", []))}  # fmt: skip
    best_params, best = bot.params, backtest.run(name, candles, bot.params, **kw)
    before = best.fitness
    rng = random.Random(f"retrain:{bot.slug}:{bot.losses}")
    for _ in range(12):
        trial = strategies.mutate(name, bot.params, rng, scale=0.35)
        res = backtest.run(name, candles, trial, **kw)
        if res.fitness > best.fitness:
            best_params, best = trial, res
    if best_params is not bot.params:
        bot.params = best_params
        bot.generation += 1
    bot.fitness = best.fitness
    bot.memory = {**bot.memory, "backtest": best.as_dict()}
    avoid = bot.memory.get("avoid", [])
    return (f"Retrained to generation {bot.generation}: fitness {before:.2f} → {best.fitness:.2f}, "
            f"backtest win rate {best.win_rate:.0%}. Avoiding: {', '.join(avoid) or 'nothing yet'}.")  # fmt: skip
