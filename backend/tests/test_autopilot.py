from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.llm.router import ModelRouter
from app.models import Task
from app.services import autopilot, tasks
from tests.fakes import free
from tests.test_ops import FOUND, _audit


@pytest.fixture
def offline(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.plugins import business_discovery, website_auditor

    monkeypatch.setattr(business_discovery, "discover", lambda *a, **k: FOUND)
    monkeypatch.setattr(website_auditor, "audit_website", _audit)


def _router(client: TestClient) -> ModelRouter:
    return client.app.state.model_router  # type: ignore[attr-defined,no-any-return]


def drain(db: Session, router: ModelRouter) -> None:
    while tasks.process_next(db, router):
        pass


def test_only_owner_switches_autopilot(
    client: TestClient, owner_headers: dict[str, str], admin_headers: dict[str, str]
) -> None:
    status = client.get("/api/autopilot", headers=admin_headers).json()
    assert status["enabled"] is True and status["cities"]  # on by default
    assert (
        client.put("/api/autopilot", json={"enabled": False}, headers=admin_headers).status_code
        == 403
    )
    r = client.put(
        "/api/autopilot", json={"enabled": False, "cities": ["Mysuru"]}, headers=owner_headers
    )
    assert r.json()["enabled"] is False and r.json()["cities"] == ["Mysuru"]
    bad = client.put("/api/autopilot", json={"categories": ["spaceships"]}, headers=owner_headers)
    assert bad.status_code == 400


def test_cycles_without_ai_report_then_discover(
    client: TestClient,
    owner_headers: dict[str, str],
    seeded: None,
    offline: None,
    settings: Settings,
    db: Session,
) -> None:
    client.app.state.model_router = ModelRouter(settings, providers=[])  # type: ignore[attr-defined]
    router = _router(client)
    client.put("/api/autopilot", headers=owner_headers, json={"enabled": False})
    assert autopilot.tick(db, router) is None  # paused by the owner
    client.put(
        "/api/autopilot",
        headers=owner_headers,
        json={"enabled": True, "cities": ["Mysuru"], "categories": ["gyms"]},
    )
    first = autopilot.tick(db, router)
    assert first is not None and first.input["workflow"] == "daily_report"
    assert autopilot.tick(db, router) is None  # not due yet
    drain(db, router)
    second = autopilot.tick(db, router, force=True)
    assert second is not None and second.input["workflow"] == "website_opportunities"
    drain(db, router)
    status = client.get("/api/autopilot", headers=owner_headers).json()
    assert status["latest_report"]["title"].startswith("CEO report")
    assert "Revenue today 0 INR" in status["latest_report"]["content"]
    assert [r["status"] for r in status["recent"]] == ["succeeded", "succeeded"]
    assert len(client.get("/api/leads", headers=owner_headers).json()) == 2
    dash = client.get("/api/dashboard", headers=owner_headers).json()
    assert dash["autopilot"]["enabled"] is True and dash["autopilot"]["cycles_today"] == 2
    events = {e["type"] for e in client.get("/api/events?limit=500", headers=owner_headers).json()}
    assert {"autopilot.cycle", "report.ready"} <= events


def test_with_ai_it_drafts_outreach_for_approval_and_never_sends(
    client: TestClient,
    owner_headers: dict[str, str],
    seeded: None,
    offline: None,
    settings: Settings,
    db: Session,
) -> None:
    provider = free(["Subject: Hi\n\nReply STOP to opt out."])
    client.app.state.model_router = ModelRouter(settings, providers=[provider])  # type: ignore[attr-defined]
    router = _router(client)
    client.put(
        "/api/autopilot",
        headers=owner_headers,
        json={"enabled": True, "cities": ["Mysuru"], "categories": ["gyms"]},
    )
    actions: list[Any] = []
    for _ in range(4):
        task = autopilot.tick(db, router, force=True)
        assert task is not None
        actions.append(task.input["workflow"])
        drain(db, router)
    # report -> no leads yet so research -> discover -> draft outreach for the best lead
    assert actions == [
        "daily_report",
        "opportunity_research",
        "website_opportunities",
        "draft_outreach",
    ]
    approvals = client.get("/api/approvals?status=pending", headers=owner_headers).json()
    assert len(approvals) == 1 and approvals[0]["kind"] == "outreach"
    assert all(
        t.status != "failed"
        for t in db.query(Task).all()
        if t.input.get("workflow") != "opportunity_research"
    )


def test_waits_for_an_owner(db: Session, settings: Settings) -> None:
    assert autopilot.tick(db, ModelRouter(settings, providers=[])) is None


def test_voice_controls_autopilot(
    client: TestClient, owner_headers: dict[str, str], viewer_headers: dict[str, str]
) -> None:
    r = client.post(
        "/api/command", json={"text": "Hey Matt, start autopilot"}, headers=owner_headers
    )
    assert r.json()["intent"] == "autopilot" and "won't send" in r.json()["reply"]
    assert client.get("/api/autopilot", headers=owner_headers).json()["enabled"] is True
    r = client.post("/api/command", json={"text": "what are you working on"}, headers=owner_headers)
    assert "Autopilot is on" in r.json()["reply"]
    r = client.post("/api/command", json={"text": "stop autopilot"}, headers=owner_headers)
    assert client.get("/api/autopilot", headers=owner_headers).json()["enabled"] is False
