"""Free market data. NSE candles from Yahoo Finance's public chart API; crypto candles from
Binance's public market-data mirror (no account or key). Prices are converted to INR.

Both sources are free and unofficial for NSE, so data can be delayed or briefly unavailable;
the swarm treats stale or missing data as "market closed" and does not trade on it.
"""

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Protocol

import httpx

from app.trading.universe import Instrument

log = logging.getLogger(__name__)

#: [epoch seconds, open, high, low, close, volume], oldest first.
Candle = list[float]

YAHOO = "https://query1.finance.yahoo.com/v8/finance/chart/{feed}?interval={interval}&range={rng}"
BINANCE = "https://data-api.binance.vision/api/v3/klines?symbol={feed}&interval={interval}&limit=300"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; MATT/0.1)", "Accept": "application/json"}
YAHOO_RANGE = {"5m": "5d", "15m": "1mo"}


class Feed(Protocol):
    def candles(self, inst: Instrument, interval: str) -> list[Candle]: ...


def parse_yahoo(data: dict[str, Any]) -> list[Candle]:
    result = (data.get("chart") or {}).get("result") or []
    if not result:
        return []
    r = result[0]
    stamps = r.get("timestamp") or []
    q = ((r.get("indicators") or {}).get("quote") or [{}])[0]
    out: list[Candle] = []
    for i, ts in enumerate(stamps):
        row = [q.get(k, [None] * len(stamps))[i] for k in ("open", "high", "low", "close", "volume")]
        if any(v is None for v in row[:4]):
            continue  # Yahoo leaves gaps as nulls
        out.append([float(ts), *(float(v or 0) for v in row)])
    return out


def parse_binance(data: list[list[Any]], usd_to_inr: float) -> list[Candle]:
    return [
        [float(k[0]) / 1000, *(float(k[i]) * usd_to_inr for i in (1, 2, 3, 4)), float(k[5])]
        for k in data
    ]


class HttpFeed:
    def __init__(self, usd_to_inr: float, get: Callable[[str], Any] | None = None) -> None:
        self.usd_to_inr = usd_to_inr
        self._get = get or self._http_get

    @staticmethod
    def _http_get(url: str) -> Any:
        r = httpx.get(url, headers=HEADERS, timeout=10)
        r.raise_for_status()
        return r.json()

    def candles(self, inst: Instrument, interval: str) -> list[Candle]:
        try:
            if inst.market == "crypto":
                return parse_binance(
                    self._get(BINANCE.format(feed=inst.feed, interval=interval)), self.usd_to_inr
                )
            url = YAHOO.format(feed=inst.feed, interval=interval, rng=YAHOO_RANGE[interval])
            return parse_yahoo(self._get(url))
        except Exception as exc:  # network, 429, bad JSON: the bot reports no data
            log.warning("market data failed", extra={"symbol": inst.symbol, "err": str(exc)})
            return []


def candle_time(c: Candle) -> datetime:
    return datetime.fromtimestamp(c[0], UTC)
