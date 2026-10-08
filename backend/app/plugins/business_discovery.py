"""Business discovery from OpenStreetMap (open data, ODbL licence: © OpenStreetMap contributors).

Uses Nominatim to find the city and the Overpass API to list businesses of a category there.
Both are public APIs used within their usage policies: one request each, identified by a
User-Agent, no scraping. Only public business details published on OSM are kept.
"""

from typing import Any

import httpx

from app.core.domain import CostTier, Permission, RiskLevel
from app.core.net import USER_AGENT
from app.plugins.base import ToolDefinition

NOMINATIM = "https://nominatim.openstreetmap.org/search"
OVERPASS = "https://overpass-api.de/api/interpreter"

#: Spec categories → OSM tag filters.
CATEGORIES: dict[str, list[str]] = {
    "restaurants": ['["amenity"~"^(restaurant|cafe|fast_food)$"]'],
    "gyms": ['["leisure"="fitness_centre"]'],
    "dentists": ['["amenity"="dentist"]', '["healthcare"="dentist"]'],
    "salons": ['["shop"~"^(hairdresser|beauty)$"]'],
    "real estate": ['["office"="estate_agent"]'],
    "construction": ['["craft"~"^(builder|carpenter)$"]', '["office"="construction_company"]'],
    "law firms": ['["office"="lawyer"]'],
    "accountants": ['["office"~"^(accountant|tax_advisor)$"]'],
    "clinics": ['["amenity"~"^(clinic|doctors)$"]'],
    "hotels": ['["tourism"~"^(hotel|guest_house)$"]'],
    "retail": ['["shop"~"^(clothes|electronics|furniture|gift|jewelry|shoes)$"]'],
    "logistics": ['["office"="logistics"]', '["shop"="courier"]'],
    "education": ['["amenity"~"^(school|college|language_school|music_school|driving_school)$"]'],
    "automotive": ['["shop"~"^(car|car_repair|car_parts|tyres)$"]'],
    "home services": ['["craft"~"^(plumber|electrician|painter|hvac)$"]'],
    "professional services": ['["office"~"^(consulting|it|architect|company)$"]'],
}


class DiscoveryError(RuntimeError):
    pass


def _client() -> httpx.Client:
    return httpx.Client(timeout=60, headers={"User-Agent": USER_AGENT})


def geocode_area(city: str, client: httpx.Client) -> int:
    r = client.get(NOMINATIM, params={"q": city, "format": "json", "limit": 5})
    r.raise_for_status()
    for place in r.json():
        if place.get("osm_type") == "relation":
            return 3_600_000_000 + int(place["osm_id"])
    raise DiscoveryError(f"Could not find an area called {city!r} on OpenStreetMap")


def discover(
    city: str, category: str, limit: int = 20, client: httpx.Client | None = None
) -> dict[str, Any]:
    category = category.lower().strip()
    filters = CATEGORIES.get(category)
    if filters is None:
        raise DiscoveryError(f"Unknown category {category!r}. Known: {', '.join(CATEGORIES)}")
    limit = max(1, min(limit, 100))
    own = client is None
    client = client or _client()
    try:
        area = geocode_area(city, client)
        selectors = "".join(f'nwr{f}["name"](area.a);' for f in filters)
        query = (
            f"[out:json][timeout:50];area({area})->.a;({selectors});out center tags {limit * 3};"
        )
        r = client.post(OVERPASS, data={"data": query})
        if r.status_code == 429:
            raise DiscoveryError("OpenStreetMap Overpass is rate limiting; try again shortly")
        r.raise_for_status()
        elements = r.json().get("elements", [])
    except httpx.HTTPError as exc:
        raise DiscoveryError(f"OpenStreetMap request failed: {exc}") from exc
    finally:
        if own:
            client.close()

    businesses: list[dict[str, Any]] = []
    for el in elements:
        tags = el.get("tags", {})
        name = tags.get("name")
        if not name:
            continue
        website = tags.get("website") or tags.get("contact:website")
        address = ", ".join(
            v for k in ("addr:housenumber", "addr:street", "addr:suburb", "addr:city")
            if (v := tags.get(k))
        )  # fmt: skip
        businesses.append(
            {
                "name": name,
                "category": category,
                "city": city,
                "country": tags.get("addr:country"),
                "location": address or None,
                "website": website,
                "public_phone": tags.get("phone") or tags.get("contact:phone"),
                "public_email": tags.get("email") or tags.get("contact:email"),
                "source": "openstreetmap",
                "source_ref": f"{el['type']}/{el['id']}",
                "source_url": f"https://www.openstreetmap.org/{el['type']}/{el['id']}",
            }
        )
    # Businesses with websites first (they can be audited), then those without (need one).
    businesses.sort(key=lambda b: b["website"] is None)
    return {
        "businesses": businesses[:limit],
        "found": len(businesses),
        "attribution": "© OpenStreetMap contributors (ODbL)",
    }


TOOL = ToolDefinition(
    slug="business_discovery",
    name="Business Discovery (OpenStreetMap)",
    description="Finds businesses by city and category from OpenStreetMap open data, with "
    "public contact details where published.",
    provider="openstreetmap",
    cost_tier=CostTier.FREE,
    permission=Permission.READ,
    risk_level=RiskLevel.LOW,
    input_schema={
        "type": "object",
        "properties": {
            "city": {"type": "string"},
            "category": {"type": "string", "enum": sorted(CATEGORIES)},
            "limit": {"type": "integer", "minimum": 1, "maximum": 100},
        },
        "required": ["city", "category"],
    },
    output_schema={"type": "object", "properties": {"businesses": {"type": "array"}}},
    run=lambda city, category, limit=20, **_: discover(city, category, limit),
)
