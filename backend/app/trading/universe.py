"""What the swarm watches. Intraday cash equities on NSE and spot crypto; no futures or options.

Low-priced, liquid NSE names are included because a small account can only buy whole shares.
Crypto is spot only and always paper-traded: it is not held in a demat account.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Instrument:
    symbol: str  # display / broker trading symbol
    market: str  # nse | crypto
    feed: str  # the data source's symbol

    @property
    def fractional(self) -> bool:
        return self.market == "crypto"


NSE = [
    "IDEA", "YESBANK", "SUZLON", "SOUTHBANK", "IDFCFIRSTB", "NHPC", "PNB", "GMRAIRPORT", "IRFC",
    "NBCC", "SAIL", "TATASTEEL", "ITC", "SBIN", "RELIANCE", "HDFCBANK", "ICICIBANK", "INFY",
    "TCS", "AXISBANK",
]  # fmt: skip
CRYPTO = ["BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "ADA", "TRX", "AVAX", "LINK"]

INSTRUMENTS: list[Instrument] = [Instrument(s, "nse", f"{s}.NS") for s in NSE] + [
    Instrument(s, "crypto", f"{s}USDT") for s in CRYPTO
]
BY_SYMBOL = {i.symbol: i for i in INSTRUMENTS}
INTERVALS = ("5m", "15m")
