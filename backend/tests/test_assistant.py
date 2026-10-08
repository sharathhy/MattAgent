from fastapi.testclient import TestClient

from app.core.config import Settings
from app.llm.router import ModelRouter


def say(client: TestClient, headers: dict[str, str], text: str) -> dict:  # type: ignore[type-arg]
    r = client.post("/api/command", json={"text": text}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()  # type: ignore[no-any-return]


def test_alexa_style_commands_without_a_model(
    client: TestClient, owner_headers: dict[str, str], seeded: None, settings: Settings
) -> None:
    client.app.state.model_router = ModelRouter(settings, providers=[])  # type: ignore[attr-defined]
    r = say(client, owner_headers, "Hey Matt, how much did we earn today?")
    assert r["intent"] == "earnings" and "₹0" in r["reply"] and "No revenue" in r["reply"]

    r = say(client, owner_headers, "record 15k payment received for a website project")
    assert r["intent"] == "record_ledger"
    assert r["reply"] == "Recorded ₹15,000 revenue for today under websites."
    r = say(client, owner_headers, "I spent 1,200 rupees on hosting")
    assert r["reply"].startswith("Recorded ₹1,200 expense")

    r = say(client, owner_headers, "what's our revenue today")
    assert "₹15,000" in r["reply"]
    dash = client.get("/api/dashboard", headers=owner_headers).json()
    assert dash["revenue"]["today_inr"] == 15000
    assert dash["earnings"]["daily"][-1]["revenue_inr"] == 15000
    assert dash["earnings"]["daily"][-1]["expense_inr"] == 1200
    assert len(dash["earnings"]["daily"]) == 30

    assert say(client, owner_headers, "open leads")["data"]["navigate"] == "/leads"
    assert say(client, owner_headers, "what's pending")["intent"] == "approvals"
    assert say(client, owner_headers, "what time is it")["intent"] == "time"
    r = say(client, owner_headers, "Remember that clinics prefer WhatsApp.")
    assert r["intent"] == "remember"
    notes = client.get("/api/knowledge", headers=owner_headers).json()
    assert notes[0]["content"] == "clinics prefer WhatsApp."
    assert say(client, owner_headers, "thank you")["intent"] == "thanks"
    # Not money: must not be logged as revenue.
    assert say(client, owner_headers, "add a task to call 5 clients")["intent"] == "no_model"


def test_revenue_attributed_to_skills(
    client: TestClient, owner_headers: dict[str, str], seeded: None
) -> None:
    from datetime import date

    entry = {"kind": "revenue", "amount_inr": "20000", "category": "websites",
             "description": "Iron Gym site", "occurred_on": date.today().isoformat(),
             "agent_slug": "sales-copywriter"}  # fmt: skip
    assert client.post("/api/ledger", json={**entry, "agent_slug": "nope"},
                       headers=owner_headers).status_code == 404  # fmt: skip
    entry_id = client.post("/api/ledger", json=entry, headers=owner_headers).json()["id"]
    skills = client.get("/api/dashboard", headers=owner_headers).json()["revenue"]["earning_skills"]
    assert skills[0]["slug"] == "sales-copywriter" and skills[0]["revenue_inr"] == 20000
    agent = client.get("/api/agents/sales-copywriter", headers=owner_headers).json()
    assert float(agent["revenue_contribution"]) == 20000
    r = say(client, owner_headers, "which skills are earning money?")
    assert r["intent"] == "earning_skills" and "Sales Copywriter" in r["reply"]
    client.delete(f"/api/ledger/{entry_id}", headers=owner_headers)
    agent = client.get("/api/agents/sales-copywriter", headers=owner_headers).json()
    assert float(agent["revenue_contribution"]) == 0
