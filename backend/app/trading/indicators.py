"""Technical indicators and candlestick patterns, in plain Python (no paid data or libraries)."""

from typing import Any

from app.trading.market import Candle


def ema(values: list[float], period: int) -> list[float]:
    if not values:
        return []
    k = 2 / (period + 1)
    out = [values[0]]
    for v in values[1:]:
        out.append(v * k + out[-1] * (1 - k))
    return out


def rsi(closes: list[float], period: int = 14) -> list[float]:
    if len(closes) < 2:
        return [50.0] * len(closes)
    gains, losses = [0.0], [0.0]
    for a, b in zip(closes, closes[1:], strict=False):
        gains.append(max(b - a, 0.0))
        losses.append(max(a - b, 0.0))
    avg_g, avg_l = ema(gains, period * 2 - 1), ema(losses, period * 2 - 1)  # Wilder smoothing
    return [100.0 if lo == 0 else 100 - 100 / (1 + g / lo) for g, lo in zip(avg_g, avg_l, strict=True)]


def atr(candles: list[Candle], period: int = 14) -> list[float]:
    trs: list[float] = []
    for i, c in enumerate(candles):
        prev = candles[i - 1][4] if i else c[4]
        trs.append(max(c[2] - c[3], abs(c[2] - prev), abs(c[3] - prev)))
    return ema(trs, period * 2 - 1)


def vwap(candles: list[Candle]) -> list[float]:
    """Session VWAP, reset each calendar day (UTC day boundaries suit both NSE and crypto)."""
    out: list[float] = []
    pv = vol = 0.0
    day = None
    for c in candles:
        d = int(c[0] // 86400)
        if d != day:
            day, pv, vol = d, 0.0, 0.0
        typical = (c[2] + c[3] + c[4]) / 3
        pv += typical * max(c[5], 1e-9)
        vol += max(c[5], 1e-9)
        out.append(pv / vol)
    return out


def bollinger(closes: list[float], period: int = 20, k: float = 2.0) -> tuple[list[float], list[float]]:
    upper, lower = [], []
    for i in range(len(closes)):
        w = closes[max(0, i - period + 1) : i + 1]
        mean = sum(w) / len(w)
        sd = (sum((x - mean) ** 2 for x in w) / len(w)) ** 0.5
        upper.append(mean + k * sd)
        lower.append(mean - k * sd)
    return upper, lower


def macd(closes: list[float]) -> tuple[list[float], list[float]]:
    line = [a - b for a, b in zip(ema(closes, 12), ema(closes, 26), strict=True)]
    return line, ema(line, 9)


def patterns(candles: list[Candle]) -> list[str]:
    """Candlestick patterns on the latest candle."""
    if len(candles) < 2:
        return []
    found: list[str] = []
    p, c = candles[-2], candles[-1]
    body, rng = abs(c[4] - c[1]), max(c[2] - c[3], 1e-9)
    lower_wick = min(c[1], c[4]) - c[3]
    upper_wick = c[2] - max(c[1], c[4])
    if body <= 0.1 * rng:
        found.append("doji")
    if lower_wick >= 2 * body and upper_wick <= body and body > 0:
        found.append("hammer")
    if upper_wick >= 2 * body and lower_wick <= body and body > 0:
        found.append("shooting_star")
    if p[4] < p[1] and c[4] > c[1] and c[4] >= p[1] and c[1] <= p[4]:
        found.append("bullish_engulfing")
    if p[4] > p[1] and c[4] < c[1] and c[4] <= p[1] and c[1] >= p[4]:
        found.append("bearish_engulfing")
    return found


def summary(candles: list[Candle]) -> dict[str, Any]:
    """Latest indicator values, as stored on a market snapshot and used as trade features."""
    if not candles:
        return {}
    closes = [c[4] for c in candles]
    e9, e21, e50 = ema(closes, 9), ema(closes, 21), ema(closes, 50)
    m, sig = macd(closes)
    up, lo = bollinger(closes)
    a = atr(candles)
    price = closes[-1]
    return {
        "price": price,
        "ema9": e9[-1], "ema21": e21[-1], "ema50": e50[-1],
        "rsi": rsi(closes)[-1], "atr": a[-1], "atr_pct": a[-1] / price * 100 if price else 0,
        "vwap": vwap(candles)[-1], "macd": m[-1], "macd_signal": sig[-1],
        "bb_upper": up[-1], "bb_lower": lo[-1],
        "trend": "up" if e21[-1] > e50[-1] else "down",
    }  # fmt: skip
