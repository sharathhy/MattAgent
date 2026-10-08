from urllib.parse import unquote

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import Business, Lead, LedgerEntry

UPI = "owner.test@ybl"  # placeholder; the real UPI ID lives only in Render


def _lead(db: Session, **kw: object) -> Lead:
    b = Business(name="Iron Gym", category="gyms", city="Mysuru", website="https://iron.example",
                 public_phone="98450 12345", source="openstreetmap", source_ref="node/1",
                 website_score=38, opportunity_score=81,
                 audit={"findings": ["No mobile layout", "No contact button"]}, **kw)  # fmt: skip
    db.add(b)
    db.flush()
    lead = Lead(business_id=b.id, status="qualified", service="Website redesign")
    db.add(lead)
    db.commit()
    return lead


def test_offer_goes_from_found_business_to_recorded_revenue(
    client: TestClient, owner_headers: dict[str, str], viewer_headers: dict[str, str],
    seeded: None, settings: Settings, db: Session,
) -> None:  # fmt: skip
    lead = _lead(db)
    assert client.get("/api/sales", headers=viewer_headers).status_code == 403
    desk = client.get("/api/sales", headers=owner_headers).json()
    offer = desk["offers"][0]
    assert not desk["upi_ready"] and offer["business"] == "Iron Gym"
    assert "No mobile layout" in offer["message"] and "Reply STOP" in offer["message"]
    assert offer["whatsapp_url"].startswith("https://wa.me/919845012345?text=")
    assert offer["email_url"] is None and offer["payment"] is None

    url = f"/api/sales/{lead.id}/price"
    r = client.post(url, json={"amount_inr": 4999}, headers=owner_headers)
    assert r.status_code == 400 and "where you get paid" in r.json()["detail"]
    settings.upi_id = UPI
    offer = client.post(url, json={"amount_inr": 4999}, headers=owner_headers).json()
    assert offer["payment"]["upi_id"] == UPI and offer["price_inr"] == 4999
    assert f"paid by UPI to {UPI}" in unquote(offer["whatsapp_url"])
    offer = client.post(url, json={"amount_inr": 3999}, headers=owner_headers).json()
    assert offer["price_inr"] == 3999  # re-pricing replaces the request

    sent = client.post(f"/api/sales/{lead.id}/sent", headers=owner_headers).json()
    assert sent["status"] == "contacted"
    paid = client.post(f"/api/sales/{lead.id}/paid", headers=owner_headers).json()
    assert paid["status"] == "won" and paid["payment"]["status"] == "received"
    revenue = db.query(LedgerEntry).all()
    assert [float(e.amount_inr) for e in revenue] == [3999.0]
    assert client.get("/api/sales", headers=owner_headers).json()["offers"] == []  # won


def test_businesses_without_public_contact_are_counted_not_listed(
    client: TestClient, owner_headers: dict[str, str], seeded: None, db: Session
) -> None:
    lead = _lead(db)
    lead.business.public_phone = None
    db.commit()
    desk = client.get("/api/sales", headers=owner_headers).json()
    assert desk["offers"] == [] and desk["without_contact"] == 1


def test_free_demo_website_is_built_hosted_and_offered(
    client: TestClient, owner_headers: dict[str, str], seeded: None, db: Session
) -> None:
    lead = _lead(db, public_email="hi@iron.example")
    lead.business.name = 'Iron <Gym> "Pro"'
    db.commit()
    offer = client.post(f"/api/sales/{lead.id}/demo", headers=owner_headers).json()
    url = offer["demo_url"]
    assert url.startswith("http://testserver/p/")
    assert f"free demo website for {lead.business.name}: {url}" in offer["message"]
    assert offer["message"].index(url) < offer["message"].index("Reply STOP")

    page = client.get(url.removeprefix("http://testserver"))
    assert page.status_code == 200 and "noindex" in page.headers["x-robots-tag"]
    assert page.headers["content-security-policy"].startswith("default-src 'none'")
    html = page.text
    assert "Iron &lt;Gym&gt; &quot;Pro&quot;" in html and "<Gym>" not in html  # escaped
    assert "tel:9845012345" in html.replace(" ", "") and "Not live yet" in html
    assert client.get("/p/not-a-real-token-at-all").status_code == 404

    again = client.post(f"/api/sales/{lead.id}/demo", headers=owner_headers).json()
    assert again["demo_url"] == url  # rebuilding keeps the same link


def test_free_samples_for_other_services(
    client: TestClient, owner_headers: dict[str, str], seeded: None, settings: Settings,
    db: Session,
) -> None:  # fmt: skip
    from app.llm.router import ModelRouter
    from tests.fakes import free

    catalog = client.get("/api/sales/services", headers=owner_headers).json()
    assert {"website", "social_media", "google_profile", "local_seo"} <= {
        c["slug"] for c in catalog
    }
    lead = _lead(db)
    posts = "# Week 1\n- Post 1: <b>Leg day</b> #fitness\n2. Post 2: New batch timings"
    client.app.state.model_router = ModelRouter(settings, providers=[free([posts])])  # type: ignore[attr-defined]
    offer = client.post(f"/api/sales/{lead.id}/demo", json={"service": "social_media"},
                        headers=owner_headers).json()  # fmt: skip
    assert offer["service"] == "Social media posts for a month" and offer["price_inr"] == 2999
    [sample] = offer["samples"]
    assert sample["service"] == "social_media" and offer["demo_url"] is None
    assert (
        f"free sample (Social media posts for a month) for Iron Gym: {sample['url']}"
        in offer["message"]
    )
    html = client.get(sample["url"].removeprefix("http://testserver")).text
    assert "<h2>Week 1</h2>" in html and "&lt;b&gt;Leg day&lt;/b&gt;" in html
    assert "<li>Post 2: New batch timings</li>" in html

    r = client.post(f"/api/sales/{lead.id}/demo", json={"service": "bitcoin"},
                    headers=owner_headers)  # fmt: skip
    assert r.status_code == 400
