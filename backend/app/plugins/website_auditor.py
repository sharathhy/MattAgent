"""Automated website audit: fetches one public page and scores it with transparent heuristics.

Scores are ESTIMATES from observable signals on the home page, not a human design review.
"""

import re
from datetime import UTC, datetime
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlsplit

from app.core.domain import CostTier, Permission, RiskLevel
from app.core.net import FetchResult, safe_fetch
from app.plugins.base import ToolDefinition

CTA_WORDS = re.compile(
    r"\b(book|appointment|contact|call|get a quote|quote|enquire|inquire|order|reserve|schedule|"
    r"buy|shop|sign up|subscribe|whatsapp)\b",
    re.I,
)
OUTDATED_TAGS = {"font", "center", "marquee", "blink", "frameset", "frame"}
SOCIAL = ("facebook.com", "instagram.com", "linkedin.com", "twitter.com", "x.com", "youtube.com")
TECH_SIGNS = {
    "wordpress": ("wp-content", "wp-includes"),
    "wix": ("wix.com", "_wixCssImports"),
    "squarespace": ("squarespace",),
    "shopify": ("cdn.shopify.com",),
    "jquery": ("jquery",),
    "bootstrap": ("bootstrap",),
    "react": ("__next", "react"),
    "google-analytics": ("googletagmanager", "google-analytics"),
}


class _Page(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self._in_title = False
        self.meta: dict[str, str] = {}
        self.h1 = 0
        self.headings = 0
        self.images = 0
        self.images_no_alt = 0
        self.links: list[str] = []
        self.forms = 0
        self.scripts = 0
        self.stylesheets = 0
        self.inline_styles = 0
        self.tables = 0
        self.outdated = 0
        self.has_nav = False
        self.has_footer = False
        self.json_ld = 0
        self.canonical = False
        self.lang = False
        self.tel = False
        self.mailto = False
        self.text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k: (v or "") for k, v in attrs}
        if tag == "html" and a.get("lang"):
            self.lang = True
        if tag == "title":
            self._in_title = True
        elif tag == "meta":
            key = (a.get("name") or a.get("property") or "").lower()
            if key:
                self.meta[key] = a.get("content", "")
        elif tag == "h1":
            self.h1 += 1
            self.headings += 1
        elif tag in ("h2", "h3"):
            self.headings += 1
        elif tag == "img":
            self.images += 1
            if not a.get("alt"):
                self.images_no_alt += 1
        elif tag == "a":
            href = a.get("href", "")
            self.links.append(href)
            self.tel |= href.startswith("tel:")
            self.mailto |= href.startswith("mailto:")
        elif tag == "form":
            self.forms += 1
        elif tag == "script":
            self.scripts += 1
            if a.get("type") == "application/ld+json":
                self.json_ld += 1
        elif tag == "link":
            rel = a.get("rel", "").lower()
            self.stylesheets += rel == "stylesheet"
            self.canonical |= rel == "canonical"
        elif tag == "table":
            self.tables += 1
        elif tag in ("nav", "header"):
            self.has_nav = True
        elif tag == "footer":
            self.has_footer = True
        if tag in OUTDATED_TAGS:
            self.outdated += 1
        if a.get("style"):
            self.inline_styles += 1

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data
        elif data.strip():
            self.text.append(data.strip())


def _clamp(v: float) -> int:
    return max(0, min(100, round(v)))


def analyze(fetch: FetchResult) -> dict[str, Any]:
    p = _Page()
    p.feed(fetch.text)
    html = fetch.text.lower()
    text = " ".join(p.text)
    findings: list[str] = []
    https = fetch.url.startswith("https://")
    viewport = "viewport" in p.meta
    title_len = len(p.title.strip())
    desc = p.meta.get("description", "")
    years = [
        int(y)
        for y in re.findall(
            r"(?:©|&copy;|copyright)\s*(?:\d{4}\s*[-\u2013]\s*)?(\d{4})", text, re.I
        )
    ]
    current_year = datetime.now(UTC).year
    stale_copyright = bool(years) and max(years) < current_year - 2

    technical = 100.0
    if not https:
        technical -= 35
        findings.append("Site is not served over HTTPS")
    if fetch.status >= 400:
        technical -= 50
        findings.append(f"Home page returned HTTP {fetch.status}")
    if not p.lang:
        technical -= 10
        findings.append("Missing page language attribute")
    if p.images and p.images_no_alt / p.images > 0.3:
        technical -= 15
        findings.append(f"{p.images_no_alt} of {p.images} images lack alt text (accessibility)")

    seo = 100.0
    if not (10 <= title_len <= 65):
        seo -= 20
        findings.append("Title is missing or a poor length" if title_len else "Missing page title")
    if not desc:
        seo -= 20
        findings.append("Missing meta description")
    if p.h1 != 1:
        seo -= 15
        findings.append(f"Page has {p.h1} H1 headings (expected 1)")
    if not p.json_ld:
        seo -= 15
        findings.append("No structured data (JSON-LD) for local SEO")
    if not p.canonical:
        seo -= 5
    if "noindex" in p.meta.get("robots", ""):
        seo -= 30
        findings.append("Page asks search engines not to index it")
    if len(text) < 300:
        seo -= 15
        findings.append("Very little text content")

    mobile = 100.0 if viewport else 30.0
    if not viewport:
        findings.append("No mobile viewport tag: likely not mobile-friendly")
    if p.tables > 3:
        mobile -= 15
        findings.append("Table-based layout signs")

    performance = 100.0
    if fetch.elapsed_ms > 3000:
        performance -= 35
        findings.append(f"Slow response ({fetch.elapsed_ms} ms)")
    elif fetch.elapsed_ms > 1500:
        performance -= 15
    if fetch.bytes > 1_500_000:
        performance -= 25
        findings.append("Heavy home page HTML")
    if p.scripts > 25:
        performance -= 15
        findings.append(f"{p.scripts} script tags")

    conversion = 40.0
    cta = len(CTA_WORDS.findall(text))
    conversion += min(cta, 4) * 8
    conversion += 12 if p.tel else 0
    conversion += 8 if p.mailto else 0
    conversion += 12 if p.forms else 0
    if not cta:
        findings.append("No clear call to action (book, call, quote…)")
    if not (p.tel or p.forms or p.mailto):
        findings.append("No easy contact path (phone link, form or email)")

    design = 85.0
    if p.outdated:
        design -= 30
        findings.append("Uses obsolete HTML tags (font/center/marquee…)")
    if p.inline_styles > 40:
        design -= 15
    if stale_copyright:
        design -= 15
        findings.append(f"Copyright year {max(years)} suggests the site is not maintained")
    if not p.has_nav:
        design -= 10
    if not p.has_footer:
        design -= 5

    ux = 80.0 + (10 if p.has_nav else -15) + (5 if p.headings >= 3 else -10)
    scores = {
        "ux": _clamp(ux),
        "design": _clamp(design),
        "seo": _clamp(seo),
        "mobile": _clamp(mobile),
        "performance": _clamp(performance),
        "conversion": _clamp(conversion),
        "technical": _clamp(technical),
    }
    weights = {"ux": 0.15, "design": 0.15, "seo": 0.2, "mobile": 0.15,
               "performance": 0.1, "conversion": 0.15, "technical": 0.1}  # fmt: skip
    overall = _clamp(sum(scores[k] * w for k, w in weights.items()))
    host = urlsplit(fetch.url).hostname or ""
    return {
        "url": fetch.url,
        "truth": "estimate",
        "method": "automated heuristics on the home page",
        "website_score": overall,
        "scores": scores,
        "findings": findings,
        "technology_stack": sorted(
            t for t, signs in TECH_SIGNS.items() if any(s in html for s in signs)
        ),
        "social_links": sorted(
            {lnk for lnk in p.links if any(s in lnk for s in SOCIAL) and host not in lnk}
        )[:10],
        "public_emails": sorted(
            {lnk[7:].split("?")[0] for lnk in p.links if lnk.startswith("mailto:")}
        )[:3],
        "title": p.title.strip()[:200],
        "response_ms": fetch.elapsed_ms,
        "audited_at": datetime.now(UTC).isoformat(),
    }


def audit_website(url: str, **fetch_kwargs: Any) -> dict[str, Any]:
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return analyze(safe_fetch(url, **fetch_kwargs))


TOOL = ToolDefinition(
    slug="website_auditor",
    name="Website Auditor",
    description="Fetches a public home page and scores UX, design, SEO, mobile, performance, "
    "conversion and technical quality with transparent heuristics.",
    provider="matt",
    cost_tier=CostTier.FREE,
    permission=Permission.READ,
    risk_level=RiskLevel.LOW,
    input_schema={"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]},
    output_schema={"type": "object", "properties": {"website_score": {"type": "integer"}}},
    run=lambda url, **_: audit_website(url),
)
