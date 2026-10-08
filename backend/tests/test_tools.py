import json
from typing import Any

import httpx
import pytest

from app.core.net import BlockedURL, check_url, safe_fetch
from app.plugins import business_discovery, website_auditor

PUBLIC = lambda _host: ["93.184.216.34"]  # noqa: E731


def _client(handler: Any) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "http://user:pw@example.com/",
        "http://example.com:8080/",
        "http://localhost/",
        "http://printer.local/",
    ],
)
def test_check_url_rejects(url: str) -> None:
    with pytest.raises(BlockedURL):
        check_url(url, PUBLIC)


@pytest.mark.parametrize("ip", ["127.0.0.1", "10.0.0.5", "169.254.169.254", "::1", "192.168.1.1"])
def test_check_url_rejects_private_addresses(ip: str) -> None:
    with pytest.raises(BlockedURL):
        check_url("https://sneaky.example/", lambda _h: [ip])


def test_redirect_to_private_address_is_blocked() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "http://internal.example/"})

    def resolve(host: str) -> list[str]:
        return ["10.0.0.1"] if host == "internal.example" else ["93.184.216.34"]

    with pytest.raises(BlockedURL):
        safe_fetch("https://public.example/", client=_client(handler), resolve=resolve)


GOOD = """<!doctype html><html><head><title>Bright Smiles Dental Clinic in Mysore</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="Family dental clinic in Mysore offering cleaning, implants and
braces with same-week appointments and transparent pricing for every treatment.">
<meta property="og:title" content="Bright Smiles"><link rel="icon" href="/f.ico">
<script type="application/ld+json">{}</script></head><body><header><nav>
<a href="/">Home</a></nav></header><main><h1>Gentle dental care</h1>
<p>Book an appointment today.</p><a href="tel:+911234">Call now</a>
<form><input name="email"></form><img src="a.webp" alt="clinic" loading="lazy">
<a href="https://instagram.com/brightsmiles">Instagram</a></main><footer>© 2026</footer>
</body></html>"""
BAD = """<html><head><title>Home</title></head><body><center><font>Welcome to our
website</font></center><table><tr><td><img src="a.jpg"></td></tr></table>
<p>Copyright 2014</p></body></html>"""


def _page(html: str) -> Any:
    return lambda r: httpx.Response(200, text=html, headers={"content-type": "text/html"})


def test_auditor_scores_good_site_above_bad_site() -> None:
    good = website_auditor.audit_website(
        "https://good.example", client=_client(_page(GOOD)), resolve=PUBLIC
    )
    bad = website_auditor.audit_website(
        "http://bad.example", client=_client(_page(BAD)), resolve=PUBLIC
    )
    assert good["truth"] == "estimate"
    assert good["website_score"] > bad["website_score"] + 25
    assert set(good["scores"]) >= {"ux", "design", "seo", "mobile", "performance", "conversion"}
    assert "https://instagram.com/brightsmiles" in good["social_links"]
    assert any("HTTPS" in f for f in bad["findings"])
    assert any("viewport" in f.lower() or "mobile" in f.lower() for f in bad["findings"])


def test_discovery_parses_overpass() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "nominatim" in request.url.host:
            return httpx.Response(200, json=[{"osm_type": "relation", "osm_id": 42}])
        assert b"3600000042" in request.content
        elements = [
            {
                "type": "node",
                "id": 1,
                "tags": {"name": "Iron Gym", "website": "https://iron.example"},
            },
            {"type": "way", "id": 2, "tags": {"name": "Flex Fitness", "phone": "+91 1"}},
            {"type": "node", "id": 3, "tags": {}},
        ]
        return httpx.Response(200, content=json.dumps({"elements": elements}))

    result = business_discovery.discover("Mysore", "gyms", client=_client(handler))
    names = [b["name"] for b in result["businesses"]]
    assert names == ["Iron Gym", "Flex Fitness"]  # website first, unnamed dropped
    assert result["businesses"][1]["source_ref"] == "way/2"
    assert "OpenStreetMap" in result["attribution"]


def test_discovery_rejects_unknown_category() -> None:
    with pytest.raises(business_discovery.DiscoveryError, match="Unknown category"):
        business_discovery.discover("Mysore", "spaceships", client=_client(_page("")))


def test_discovery_survives_unreachable_servers() -> None:
    hosts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        hosts.append(request.url.host)
        if request.url.host in ("nominatim.openstreetmap.org", "overpass-api.de"):
            raise httpx.ConnectError("[Errno 101] Network is unreachable", request=request)
        if b"boundary" in request.content:  # city lookup through Overpass instead of Nominatim
            return httpx.Response(200, json={"elements": [{"type": "relation", "id": 42}]})
        assert b"3600000042" in request.content
        return httpx.Response(200, json={"elements": [{"type": "node", "id": 1,
                                                       "tags": {"name": "Iron Gym"}}]})  # fmt: skip

    result = business_discovery.discover("Mysore", "gyms", client=_client(handler))
    assert [b["name"] for b in result["businesses"]] == ["Iron Gym"]
    assert "overpass.private.coffee" in hosts

    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("[Errno 101] Network is unreachable", request=request)

    with pytest.raises(business_discovery.DiscoveryError, match=r"overpass\.kumi\.systems"):
        business_discovery.discover("Mysore", "gyms", client=_client(down))
