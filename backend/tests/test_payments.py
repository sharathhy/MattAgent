import inspect
import re

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core import money
from app.core.config import Settings
from app.services import payments, tasks
from app.services.errors import ServiceError

UPI = "owner.test@ybl"  # placeholder; the real UPI ID lives only in Render


def test_money_rule_blocks_outbound_and_allows_inbound() -> None:
    for text in ["transfer 5000 rupees to my bank", "withdraw the money", "refund the customer",
                 "pay the vendor 2000 inr", "debit my account", "send funds to Ravi"]:  # fmt: skip
        assert money.is_outbound(text), text
    for text in ["send a payment request for 5000", "send the invoice for payment",
                 "record a payment of 15000 from a website project", "find dentists in Mysore",
                 "how much did we earn today"]:  # fmt: skip
        assert not money.is_outbound(text), text


def test_no_code_path_moves_money_out() -> None:
    names = [n for n, _ in inspect.getmembers(payments, inspect.isfunction)]
    assert not [n for n in names if re.search(r"send|transfer|withdraw|refund|debit|payout", n)]


def test_tasks_and_voice_refuse_outbound_money(
    client: TestClient, owner_headers: dict[str, str], seeded: None, db: Session
) -> None:
    try:
        tasks.create(db, objective="Transfer 10,000 rupees to the vendor", created_by="1")
        raise AssertionError("must refuse")
    except money.OutboundMoneyBlocked:
        pass
    r = client.post("/api/tasks", headers=owner_headers, json={"objective": "withdraw all funds"})
    assert r.status_code == 403 and "only receives money" in r.json()["detail"]
    r = client.post(
        "/api/command", headers=owner_headers, json={"text": "Hey Matt, pay 500 rupees to Ravi"}
    )
    assert r.json()["intent"] == "money_rule"


def test_payment_request_needs_upi_id(client: TestClient, owner_headers: dict[str, str]) -> None:
    assert client.get("/api/payments/config", headers=owner_headers).json()["configured"] is False
    r = client.post(
        "/api/payments", headers=owner_headers, json={"amount_inr": "5000", "purpose": "Website"}
    )
    assert r.status_code == 400 and "MATT_UPI_ID" in r.json()["detail"]


def test_request_then_owner_confirms_receipt(
    client: TestClient, owner_headers: dict[str, str], admin_headers: dict[str, str],
    settings: Settings,
) -> None:  # fmt: skip
    settings.upi_id, settings.upi_payee_name = UPI, "Sharath Studio"
    body = {"amount_inr": "15000", "purpose": "Website for Mysore Dental"}
    r = client.post("/api/payments", headers=admin_headers, json=body)
    assert r.status_code == 201
    req = r.json()
    assert req["status"] == "requested" and req["reference"] == "MATT000001"
    assert req["upi_link"].startswith(
        "upi://pay?pa=owner.test%40ybl&pn=Sharath%20Studio&am=15000.00"
    )
    assert "&cu=INR" in req["upi_link"] and req["qr_svg"].lstrip().startswith("<svg")
    # Requesting money is not revenue until the owner confirms it arrived.
    assert client.get("/api/dashboard", headers=owner_headers).json()["revenue"]["month_inr"] == 0
    assert (
        client.post(
            f"/api/payments/{req['id']}/received", headers=admin_headers, json={}
        ).status_code
        == 403
    )
    done = client.post(f"/api/payments/{req['id']}/received", headers=owner_headers, json={}).json()
    assert done["status"] == "received" and done["ledger_entry_id"]
    assert (
        float(client.get("/api/dashboard", headers=owner_headers).json()["revenue"]["month_inr"])
        == 15000
    )
    again = client.post(f"/api/payments/{req['id']}/received", headers=owner_headers, json={})
    assert again.status_code == 409


def test_bad_upi_id_and_amount_limits(settings: Settings, db: Session) -> None:
    settings.upi_id = "9999999999"  # a bare phone number is not a UPI ID
    assert payments.config(settings)["problem"] == "MATT_UPI_ID is not a valid UPI ID"
    settings.upi_id = UPI
    from decimal import Decimal

    from app.models import User

    user = User(email="o@example.com", role="owner", full_name="O", password_hash="x")
    db.add(user)
    db.commit()
    try:
        payments.create(db, settings, user, amount_inr=Decimal("500000"), purpose="Big")
        raise AssertionError("must refuse")
    except ServiceError as exc:
        assert "between" in str(exc)
