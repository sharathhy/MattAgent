"""Fetch a public web page as untrusted text."""

import re
from html import unescape
from typing import Any

from app.core.domain import CostTier, Permission, RiskLevel
from app.core.net import safe_fetch
from app.plugins.base import ToolDefinition

_TAGS = re.compile(r"<(script|style)[^>]*>.*?</\1>|<[^>]+>", re.S | re.I)


def fetch_text(url: str, max_chars: int = 20_000) -> dict[str, Any]:
    result = safe_fetch(url)
    text = re.sub(r"\s+", " ", unescape(_TAGS.sub(" ", result.text))).strip()
    return {"url": result.url, "status": result.status, "text": text[:max_chars], "untrusted": True}


TOOL = ToolDefinition(
    slug="web_fetch",
    name="Web Fetch",
    description="Fetches a public web page and returns its visible text, marked untrusted. "
    "Private and internal addresses are blocked.",
    provider="matt",
    cost_tier=CostTier.FREE,
    permission=Permission.READ,
    risk_level=RiskLevel.LOW,
    input_schema={"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]},
    output_schema={"type": "object", "properties": {"text": {"type": "string"}}},
    run=lambda url, **_: fetch_text(url),
)
