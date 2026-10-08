from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.llm.router import ModelRouter
from app.models import Business, Event, Lead
from app.services import mailer, outreach

UPI = "owner.test@ybl"  # placeholder; the real UPI ID lives only in Render


def _lead(db: Session, email: str | None = "hi@iron.example", ref: str = "node/1") -> Lead:
    b = Business(name="Iron Gym", category="gyms", city="Mysuru", website="https://iron.example",
                 public_email=email, source="openstreetmap", source_ref=ref, website_score=38,
                 opportunity_score=81, audit={"findings": ["No mobile layout"]})  # fmt: skip
    db.add(b)
    db.flush()
    lead = Lead(business_id=b.id, status="qualified", service="Website redesign")
    db.add(lead)
    db.commit()
    return lead


@pytest.fixture
def outbox(monkeypatch: pytest.MonkeyPatch, settings: Settings) -> list[mailer.Mail]:
    """Configured sending, with the network call replaced by a list."""
    sent: list[mailer.Mail] = []
    settings.brevo_api_key = "test-key"
    settings.mail_from = "owner@example.com"
    settings.public_url = "https://matt.example"
    settings.worker_enabled = True
    monkeypatch.setattr(outreach, "SWITCHED_ON", True)

    def fake(settings: Settings, mail: mailer.Mail) -> str:
        sent.append(mail)
        return "brevo"

    monkeypatch.setattr(mailer, "send", fake)
    return sent


def test_sending_stays_off_until_an_email_is_connected(
    settings: Settings, db: Session, seeded: None
) -> None:
    _lead(db)
    state = outreach.status(db, settings)
    assert not state["enabled"] and "MATT_BREVO_API_KEY" in state["missing"][1]
    assert outreach.run(db, ModelRouter(settings, providers=[])) is None


def test_offer_then_one_follow_up_then_nothing(
    outbox: list[mailer.Mail], owner_headers: dict[str, str], settings: Settings, db: Session,
    seeded: None,
) -> None:  # fmt: skip
    settings.upi_id = UPI
    lead = _lead(db)
    _lead(db, email=None, ref="node/2")  # no public email: never written to
    router = ModelRouter(settings, providers=[])

    assert outreach.run(db, router) == "Emailed an offer to Iron Gym"
    mail = outbox[0]
    assert mail.to == "hi@iron.example" and "No mobile layout" in mail.body
    assert "https://matt.example/p/" in mail.body  # the free demo website
    assert f"UPI to {UPI}" in mail.body and "STOP" not in mail.body
    assert mail.unsubscribe_url in mail.body and "[Your name]" not in mail.body
    db.refresh(lead)
    assert lead.status == "contacted" and lead.business.outreach_status == "emailed"

    assert outreach.run(db, router) is None  # nothing new, follow-up not due yet
    for ev in db.query(Event).filter(Event.type == outreach.SENT):
        ev.created_at = ev.created_at - timedelta(days=4)
    db.commit()
    assert outreach.run(db, router) == "Emailed a follow-up to Iron Gym"
    assert outbox[1].subject.startswith("Re: ") and "last time" in outbox[1].body
    assert outreach.run(db, router) is None and len(outbox) == 2


def test_daily_cap_and_failures_hold_sending(
    outbox: list[mailer.Mail], monkeypatch: pytest.MonkeyPatch, settings: Settings,
    db: Session, seeded: None,
) -> None:  # fmt: skip
    for i in range(3):
        _lead(db, email=f"shop{i}@example.com", ref=f"node/{i}")
    router = ModelRouter(settings, providers=[])
    settings.auto_send_daily_cap = 1
    assert outreach.run(db, router) and outreach.run(db, router) is None
    assert len(outbox) == 1

    settings.auto_send_daily_cap = 10

    def broken(settings: Settings, mail: mailer.Mail) -> str:
        raise mailer.MailError("Brevo refused the email (401)")

    monkeypatch.setattr(mailer, "send", broken)
    assert outreach.run(db, router) is None
    assert "401" in str(outreach.status(db, settings)["last_error"])
    monkeypatch.setattr(mailer, "send", lambda s, m: outbox.append(m) or "brevo")
    assert outreach.run(db, router) is None  # backing off after a failure


def test_unsubscribe_link_stops_all_contact(
    client: TestClient, outbox: list[mailer.Mail], settings: Settings, db: Session,
    seeded: None,
) -> None:  # fmt: skip
    lead = _lead(db)
    router = ModelRouter(settings, providers=[])
    outreach.run(db, router)
    path = outbox[0].unsubscribe_url.removeprefix("https://matt.example")
    assert client.get(path[:-2] + "xx").status_code == 404
    page = client.post(path)  # one-click, as mail apps send it
    assert page.status_code == 200 and "unsubscribed" in page.text
    assert "script-src" not in page.headers["content-security-policy"]
    db.refresh(lead)
    assert lead.status == "lost" and lead.business.outreach_status == "opted_out"
    assert outreach.suppressed(db, "HI@iron.example")

    again = _lead(db, ref="node/9")  # same address listed again elsewhere
    assert again.business.public_email == "hi@iron.example"
    assert outreach.run(db, router) is None and len(outbox) == 1
