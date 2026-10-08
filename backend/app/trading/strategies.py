"""Intraday strategies. Each turns candles into a per-candle signal: +1 buy, -1 sell short, 0 none.

Every strategy has a parameter space the strategist bots search and mutate when they retrain.
All share ``stop_atr`` (stop distance in ATRs) and ``rr`` (target as a multiple of the stop).
"""

import random
from collections.abc import Callable
from typing import Any

from app.trading import indicators as ind
from app.trading.market import Candle

Params = dict[str, float]
Signals = Callable[[list[Candle], Params], list[int]]

COMMON: dict[str, tuple[float, float, bool]] = {"stop_atr": (1.0, 3.0, False), "rr": (1.0, 3.0, False)}


def _cross(a: list[float], b: list[float], i: int) -> int:
    if i == 0:
        return 0
    if a[i - 1] <= b[i - 1] and a[i] > b[i]:
        return 1
    if a[i - 1] >= b[i - 1] and a[i] < b[i]:
        return -1
    return 0


def ema_cross(c: list[Candle], p: Params) -> list[int]:
    closes = [x[4] for x in c]
    f, s, t = ind.ema(closes, int(p["fast"])), ind.ema(closes, int(p["slow"])), ind.ema(closes, 50)
    out = []
    for i in range(len(c)):
        x = _cross(f, s, i)
        out.append(x if (x > 0 and closes[i] > t[i]) or (x < 0 and closes[i] < t[i]) else 0)
    return out


def rsi_reversion(c: list[Candle], p: Params) -> list[int]:
    r = ind.rsi([x[4] for x in c], int(p["period"]))
    lo, hi = p["low"], 100 - p["low"]
    return [1 if i and r[i - 1] < lo <= r[i] else -1 if i and r[i - 1] > hi >= r[i] else 0
            for i in range(len(c))]  # fmt: skip


def vwap_trend(c: list[Candle], p: Params) -> list[int]:
    closes = [x[4] for x in c]
    v, e = ind.vwap(c), ind.ema(closes, int(p["ema"]))
    out = []
    for i in range(len(c)):
        x = _cross(closes, v, i)
        slope = e[i] - e[i - 1] if i else 0
        out.append(x if (x > 0 and slope > 0) or (x < 0 and slope < 0) else 0)
    return out


def orb(c: list[Candle], p: Params) -> list[int]:
    """Opening-range breakout: the first N candles of each day set the range."""
    n = int(p["bars"])
    out, day, hi, lo, count, fired = [], None, 0.0, 0.0, 0, False
    for x in c:
        d = int(x[0] // 86400)
        if d != day:
            day, hi, lo, count, fired = d, x[2], x[3], 0, False
        count += 1
        if count <= n:
            hi, lo = max(hi, x[2]), min(lo, x[3])
            out.append(0)
            continue
        sig = 1 if x[4] > hi else -1 if x[4] < lo else 0
        if sig and not fired:
            fired = True
            out.append(sig)
        else:
            out.append(0)
    return out


def bollinger_reversion(c: list[Candle], p: Params) -> list[int]:
    closes = [x[4] for x in c]
    up, lo = ind.bollinger(closes, int(p["period"]), p["k"])
    return [1 if i and closes[i - 1] < lo[i - 1] and closes[i] >= lo[i]
            else -1 if i and closes[i - 1] > up[i - 1] and closes[i] <= up[i] else 0
            for i in range(len(c))]  # fmt: skip


def macd_momentum(c: list[Candle], p: Params) -> list[int]:
    m, s = ind.macd([x[4] for x in c])
    out = []
    for i in range(len(c)):
        x = _cross(m, s, i)
        gap = p["min_gap"] * abs(s[i]) / 10
        ok = (x > 0 and m[i] > gap) or (x < 0 and m[i] < -gap)
        out.append(x if ok else 0)
    return out


def engulfing_trend(c: list[Candle], p: Params) -> list[int]:
    closes = [x[4] for x in c]
    t = ind.ema(closes, int(p["trend"]))
    out = []
    for i in range(len(c)):
        pats = ind.patterns(c[max(0, i - 1) : i + 1])
        if "bullish_engulfing" in pats and closes[i] > t[i]:
            out.append(1)
        elif "bearish_engulfing" in pats and closes[i] < t[i]:
            out.append(-1)
        else:
            out.append(0)
    return out


def volume_breakout(c: list[Candle], p: Params) -> list[int]:
    n, k = int(p["lookback"]), p["vol_mult"]
    out = []
    for i in range(len(c)):
        if i < n:
            out.append(0)
            continue
        w = c[i - n : i]
        avg_vol = sum(x[5] for x in w) / n
        loud = c[i][5] > k * avg_vol
        if loud and c[i][4] > max(x[2] for x in w):
            out.append(1)
        elif loud and c[i][4] < min(x[3] for x in w):
            out.append(-1)
        else:
            out.append(0)
    return out


STRATEGIES: dict[str, tuple[Signals, dict[str, tuple[float, float, bool]], str]] = {
    "ema_cross": (ema_cross, {"fast": (5, 12, True), "slow": (15, 40, True)},
                  "Fast EMA crosses slow EMA in the direction of the 50 EMA trend"),
    "rsi_reversion": (rsi_reversion, {"period": (7, 21, True), "low": (20, 35, False)},
                      "Buy when RSI climbs back out of oversold, short out of overbought"),
    "vwap_trend": (vwap_trend, {"ema": (9, 30, True)},
                   "Price crosses VWAP with the EMA sloping the same way"),
    "orb": (orb, {"bars": (2, 6, True)}, "Opening-range breakout of the first candles of the day"),
    "bollinger_reversion": (bollinger_reversion, {"period": (14, 30, True), "k": (1.6, 2.6, False)},
                            "Re-entry into the Bollinger band after closing outside it"),
    "macd_momentum": (macd_momentum, {"min_gap": (0, 1, False)},
                      "MACD crosses its signal line on the same side of zero"),
    "engulfing_trend": (engulfing_trend, {"trend": (20, 60, True)},
                        "Engulfing candle in the direction of the trend"),
    "volume_breakout": (volume_breakout, {"lookback": (10, 30, True), "vol_mult": (1.3, 3.0, False)},
                        "Range breakout on unusually high volume"),
}  # fmt: skip


def space(name: str) -> dict[str, tuple[float, float, bool]]:
    return {**STRATEGIES[name][1], **COMMON}


def random_params(name: str, rng: random.Random) -> Params:
    out: Params = {}
    for key, (lo, hi, integer) in space(name).items():
        out[key] = float(rng.randint(int(lo), int(hi))) if integer else round(rng.uniform(lo, hi), 2)
    return out


def mutate(name: str, params: Params, rng: random.Random, scale: float = 0.25) -> Params:
    """Nudge each parameter by up to ``scale`` of its range, staying inside the range."""
    out: Params = {}
    for key, (lo, hi, integer) in space(name).items():
        v = params.get(key, (lo + hi) / 2) + rng.uniform(-scale, scale) * (hi - lo)
        v = min(max(v, lo), hi)
        out[key] = float(round(v)) if integer else round(v, 2)
    return out


def signals(name: str, candles: list[Candle], params: Params) -> list[int]:
    fn = STRATEGIES[name][0]
    return fn(candles, params)


def describe() -> list[dict[str, Any]]:
    return [{"name": k, "about": v[2], "params": list(space(k))} for k, v in STRATEGIES.items()]
