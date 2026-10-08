"""News bots: free headlines from Google News RSS, scored with a finance word list.

Scoring is a simple lexicon, not a model, so it costs nothing and runs every cycle. It is a
weak signal: traders only use it to lean, never as the reason for a trade on its own.
"""

import re
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from datetime import datetime
from urllib.parse import quote_plus

import httpx

from app.trading.universe import Instrument

RSS = "https://news.google.com/rss/search?q={q}&hl=en-IN&gl=IN&ceid=IN:en"
CRYPTO_NAMES = {"BTC": "Bitcoin", "ETH": "Ethereum", "SOL": "Solana", "BNB": "BNB", "XRP": "XRP",
                "DOGE": "Dogecoin", "ADA": "Cardano", "TRX": "Tron", "AVAX": "Avalanche",
                "LINK": "Chainlink"}  # fmt: skip
POSITIVE = {
    "surge", "surges", "soar", "soars", "jump", "jumps", "rally", "rallies", "gain", "gains",
    "beat", "beats", "record", "upgrade", "upgraded", "buy", "bullish", "profit", "growth",
    "rise", "rises", "high", "strong", "order", "wins", "approval", "outperform", "dividend",
}  # fmt: skip
NEGATIVE = {
    "fall", "falls", "drop", "drops", "plunge", "plunges", "slump", "crash", "loss", "losses",
    "miss", "misses", "downgrade", "downgraded", "sell", "bearish", "weak", "probe", "fraud",
    "ban", "penalty", "default", "lawsuit", "hack", "hacked", "low", "decline", "cut", "raid",
}  # fmt: skip
WORD = re.compile(r"[a-z]+")


@dataclass(frozen=True)
class Headline:
    title: str
    url: str
    published: datetime | None
    sentiment: float


def score(text: str) -> float:
    words = WORD.findall(text.lower())
    pos = sum(w in POSITIVE for w in words)
    neg = sum(w in NEGATIVE for w in words)
    return 0.0 if pos == neg else round((pos - neg) / (pos + neg), 3)


def query(inst: Instrument) -> str:
    if inst.market == "crypto":
        return f"{CRYPTO_NAMES.get(inst.symbol, inst.symbol)} crypto price"
    return f"{inst.symbol} NSE share"


def parse(xml: str, limit: int = 8) -> list[Headline]:
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return []
    out: list[Headline] = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        if not title:
            continue
        try:
            published = parsedate_to_datetime(item.findtext("pubDate") or "")
        except (TypeError, ValueError):
            published = None
        out.append(Headline(title[:500], (item.findtext("link") or "")[:1000], published,
                            score(title)))  # fmt: skip
        if len(out) >= limit:
            break
    return out


def fetch(inst: Instrument, get: Callable[[str], str] | None = None) -> list[Headline]:
    url = RSS.format(q=quote_plus(query(inst)))
    try:
        text = get(url) if get else httpx.get(url, timeout=10, headers={
            "User-Agent": "Mozilla/5.0 (compatible; MATT/0.1)"}).text  # fmt: skip
    except Exception:
        return []
    return parse(text)
