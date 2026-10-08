"""Scoring formulas. Inputs are labelled estimates; the formula itself is transparent."""

from decimal import Decimal

#: Opportunity Score = demand + revenue + competition advantage + feasibility + recurring
#: + automation - cost - risk - time to revenue. Each factor is rated 0-10.
POSITIVE_FACTORS = (
    "market_demand",
    "revenue_potential",
    "competition_advantage",
    "execution_feasibility",
    "recurring_revenue",
    "automation_potential",
)
NEGATIVE_FACTORS = ("cost", "risk", "time_to_revenue")
FACTORS = POSITIVE_FACTORS + NEGATIVE_FACTORS


def opportunity_score(factors: dict[str, float]) -> float:
    """Raw score ranges from -30 to 60; it is rescaled to 0-100."""
    clean = {k: max(0.0, min(10.0, float(factors.get(k, 0)))) for k in FACTORS}
    raw = sum(clean[k] for k in POSITIVE_FACTORS) - sum(clean[k] for k in NEGATIVE_FACTORS)
    return round((raw + 30) / 90 * 100, 1)


#: Typical small-business website project ranges in India. An ASSUMPTION, not a quote.
SERVICE_VALUE_INR = {
    "New website": (Decimal("10000"), Decimal("40000")),
    "Website redesign": (Decimal("15000"), Decimal("60000")),
    "Website improvements": (Decimal("5000"), Decimal("20000")),
}


def website_lead(website: str | None, website_score: int | None) -> tuple[str, float] | None:
    """Decide whether a business is a website lead. Returns (service, opportunity 0-100)."""
    if not website:
        return "New website", 70.0
    if website_score is None:
        return None
    if website_score < 50:
        return "Website redesign", float(100 - website_score)
    if website_score < 70:
        return "Website improvements", float(100 - website_score) * 0.8
    return None
