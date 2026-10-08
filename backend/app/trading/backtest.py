"""Backtest one strategy on recent candles, intraday rules included.

Entry at the next candle's open after a signal. Stop at ``stop_atr`` ATRs, target at ``rr`` times
the stop. If a candle touches both, the stop is assumed hit first (conservative). Positions are
closed at the last candle of each day: nothing is carried overnight. Costs are deducted.
"""

from dataclasses import dataclass, field
from typing import Any

from app.trading import indicators as ind
from app.trading import strategies
from app.trading.market import Candle


@dataclass
class Result:
    trades: int = 0
    wins: int = 0
    losses: int = 0
    return_pct: float = 0.0  # sum of per-trade returns, % of position value
    max_drawdown_pct: float = 0.0
    log: list[dict[str, Any]] = field(default_factory=list)

    @property
    def win_rate(self) -> float:
        return self.wins / self.trades if self.trades else 0.0

    @property
    def expectancy_pct(self) -> float:
        return self.return_pct / self.trades if self.trades else 0.0

    @property
    def fitness(self) -> float:
        """Rewards steady net profit, not win rate alone: a 90% win rate that loses money scores
        badly. Few trades are discounted because they prove little."""
        if not self.trades:
            return 0.0
        confidence = min(self.trades, 20) / 20
        return round((self.return_pct - 0.5 * self.max_drawdown_pct) * confidence, 4)

    def as_dict(self) -> dict[str, Any]:
        return {
            "trades": self.trades,
            "wins": self.wins,
            "losses": self.losses,
            "win_rate": round(self.win_rate, 3),
            "return_pct": round(self.return_pct, 3),
            "expectancy_pct": round(self.expectancy_pct, 4),
            "max_drawdown_pct": round(self.max_drawdown_pct, 3),
            "fitness": self.fitness,
        }


def levels(side: int, entry: float, atr: float, params: dict[str, float]) -> tuple[float, float]:
    dist = max(atr * params.get("stop_atr", 1.5), entry * 0.001)
    return entry - side * dist, entry + side * dist * params.get("rr", 1.5)


def run(
    name: str,
    candles: list[Candle],
    params: dict[str, float],
    *,
    cost_pct: float,
    allow_short: bool = True,
    avoid: list[str] | None = None,
) -> Result:
    res = Result()
    if len(candles) < 30:
        return res
    sig = strategies.signals(name, candles, params)
    atrs = ind.atr(candles)
    feats = feature_series(candles)
    equity = peak = 0.0
    i = 1
    while i < len(candles) - 1:
        s = sig[i]
        if s == 0 or (s < 0 and not allow_short) or (avoid and bucket(s, feats[i]) in avoid):
            i += 1
            continue
        entry = candles[i + 1][1]
        stop, target = levels(s, entry, atrs[i], params)
        day = int(candles[i + 1][0] // 86400)
        j, exit_price, reason = i + 1, candles[-1][4], "end"
        while j < len(candles):
            c = candles[j]
            if int(c[0] // 86400) != day:
                exit_price, reason = candles[j - 1][4], "square_off"
                j -= 1
                break
            if (s > 0 and c[3] <= stop) or (s < 0 and c[2] >= stop):
                exit_price, reason = stop, "stop"
                break
            if (s > 0 and c[2] >= target) or (s < 0 and c[3] <= target):
                exit_price, reason = target, "target"
                break
            j += 1
        ret = s * (exit_price - entry) / entry * 100 - cost_pct * 100
        res.trades += 1
        res.wins += ret > 0
        res.losses += ret <= 0
        res.return_pct += ret
        equity += ret
        peak = max(peak, equity)
        res.max_drawdown_pct = max(res.max_drawdown_pct, peak - equity)
        if len(res.log) < 50:
            res.log.append(
                {"at": candles[i + 1][0], "side": s, "ret": round(ret, 3), "exit": reason}
            )
        i = max(j, i + 1) + 1
    return res


def feature_series(candles: list[Candle]) -> list[dict[str, Any]]:
    """Market conditions at each candle, used to learn which conditions lose money."""
    closes = [c[4] for c in candles]
    e21, e50, r, a = ind.ema(closes, 21), ind.ema(closes, 50), ind.rsi(closes), ind.atr(candles)
    return [
        {
            "trend": "up" if e21[i] > e50[i] else "down",
            "rsi": "high" if r[i] > 65 else "low" if r[i] < 35 else "mid",
            "vol": "high" if closes[i] and a[i] / closes[i] > 0.006 else "low",
        }
        for i in range(len(candles))
    ]


def bucket(side: int, features: dict[str, Any]) -> str:
    """A coarse market-condition label, e.g. ``long|down|high|mid``."""
    return "|".join(
        [
            "long" if side > 0 else "short",
            str(features.get("trend")),
            str(features.get("vol")),
            str(features.get("rsi")),
        ]
    )
