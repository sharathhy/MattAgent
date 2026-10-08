"""Trading hours. Intraday only: entries inside a window, everything squared off before close.

NSE cash market: 09:15 to 15:30 IST, Monday to Friday. MATT opens no new positions before 09:20
or after 14:45 and squares off at 15:10, before the broker's own auto square-off. Exchange
holidays aren't listed here; on a holiday the data goes stale and stale data blocks trading.
Crypto trades all day, but MATT keeps it intraday too: no entries after 23:00 IST and
everything closed at 23:30 IST.
"""

from datetime import datetime, time
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
NSE_OPEN, NSE_ENTRY_FROM, NSE_ENTRY_UNTIL, NSE_SQUARE_OFF = (
    time(9, 15),
    time(9, 20),
    time(14, 45),
    time(15, 10),
)
CRYPTO_ENTRY_UNTIL, CRYPTO_SQUARE_OFF = time(23, 0), time(23, 30)


def ist(now: datetime) -> datetime:
    return now.astimezone(IST)


def trading_day(now: datetime) -> str:
    return ist(now).date().isoformat()


def can_enter(market: str, now: datetime) -> bool:
    t = ist(now)
    if market == "crypto":
        return t.time() < CRYPTO_ENTRY_UNTIL
    return t.weekday() < 5 and NSE_ENTRY_FROM <= t.time() <= NSE_ENTRY_UNTIL


def must_square_off(market: str, now: datetime) -> bool:
    t = ist(now)
    if market == "crypto":
        return t.time() >= CRYPTO_SQUARE_OFF
    return t.weekday() >= 5 or t.time() >= NSE_SQUARE_OFF or t.time() < NSE_OPEN


def nse_open(now: datetime) -> bool:
    t = ist(now)
    return t.weekday() < 5 and NSE_OPEN <= t.time() < time(15, 30)
