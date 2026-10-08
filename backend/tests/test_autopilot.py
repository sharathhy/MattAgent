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


def test_with_ai_it_drafts_outreach_and_never_sends(
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
    # Outreach is not money, so it needs no approval; MATT never sends it.
    assert client.get("/api/approvals?status=pending", headers=owner_headers).json() == []
    statuses = [
        ld["business"]["outreach_status"]
        for ld in client.get("/api/leads", headers=owner_headers).json()
    ]
    assert "ready" in statuses
    assert all(
        t.status != "failed"
        for t in db.query(Task).all()
        if t.input.get("workflow") not in ("opportunity_research", "skill_bot")
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


def test_rows_left_off_by_an_old_version_turn_on(db: Session) -> None:
    from app.models import Autopilot

    db.add(Autopilot(enabled=False, cities=["Mysuru"], categories=["gyms"]))
    db.commit()
    assert autopilot.get(db).enabled is True


def test_each_cycle_gives_a_skill_its_own_turn(
    client: TestClient,
    owner_headers: dict[str, str],
    seeded: None,
    settings: Settings,
    db: Session,
) -> None:
    client.app.state.model_router = ModelRouter(settings, providers=[free()])  # type: ignore[attr-defined]
    router = _router(client)
    autopilot.tick(db, router, force=True)
    bots = [t for t in db.query(Task).all() if t.input.get("workflow") == "skill_bot"]
    assert len(bots) == 1 and bots[0].created_by == "autopilot"
    status = client.get("/api/autopilot", headers=owner_headers).json()
    assert status["bots_today"] == 1 and status["last_tick_at"] and status["free_models_only"]
    row = autopilot.get(db)
    row.daily_bot_tasks = 1
    db.commit()
    autopilot.tick(db, router, force=True)
    assert len([t for t in db.query(Task).all() if t.input.get("workflow") == "skill_bot"]) == 1


IDEA = (
    '{"name": "Clinic website audit pack", "hypothesis": "Clinics pay for a quick fix list", '
    '"target": "dental clinics in Mysuru", "plan": ["write offer", "draft audit template", '
    '"prepare outreach"], "needs_money": false, "cost_inr": 0, '
    '"expected": "2 sales of 3,000 INR in a month"}'
)


def test_skill_proposes_runs_and_hands_off_its_own_idea(
    seeded: None, owner_headers: dict[str, str], settings: Settings, db: Session
) -> None:
    from app.models import Approval, Experiment, Knowledge
    from app.workflows import Context, run_workflow

    handoff = "Template: ...\nOWNER: post the offer in two local clinic groups"
    provider = free([IDEA, "Offer: ...\nNEXT: draft the template", handoff])
    ctx = Context(db=db, router=ModelRouter(settings, providers=[provider]))
    params = {"agent_slug": "sales-copywriter"}
    out = run_workflow(ctx, "skill_bot", params)
    exp = db.get(Experiment, out["experiment_id"])
    assert exp and exp.status == "running" and exp.agent_slug == "sales-copywriter"
    assert exp.expected and exp.expected.startswith("ESTIMATE")
    assert not db.query(Approval).all()  # free idea: no approval needed
    run_workflow(ctx, "skill_bot", params)
    run_workflow(ctx, "skill_bot", params)
    db.refresh(exp)
    assert exp.status == "completed" and exp.steps_done == 2
    assert exp.result and "post the offer" in exp.result and "no revenue counts" in exp.result
    assert len(db.query(Knowledge).filter(Knowledge.kind == "agent").all()) == 2


def test_ideas_that_need_money_wait_for_the_owner(
    client: TestClient,
    owner_headers: dict[str, str],
    admin_headers: dict[str, str],
    seeded: None,
    settings: Settings,
    db: Session,
) -> None:
    from app.models import Experiment
    from app.workflows import Context, run_workflow

    idea = IDEA.replace(
        '"needs_money": false, "cost_inr": 0', '"needs_money": true, "cost_inr": 2000'
    )
    ctx = Context(db=db, router=ModelRouter(settings, providers=[free([idea])]))
    exp_id = run_workflow(ctx, "skill_bot", {"agent_slug": "sales-copywriter"})["experiment_id"]
    assert db.get(Experiment, exp_id).status == "planned"  # type: ignore[union-attr]
    pending = client.get("/api/approvals?status=pending", headers=owner_headers).json()
    assert len(pending) == 1 and pending[0]["kind"] == "investment"
    assert pending[0]["risk_level"] == "high" and "₹2,000" in pending[0]["action"]
    url = f"/api/approvals/{pending[0]['id']}/decide"
    assert client.post(url, json={"approve": True}, headers=admin_headers).status_code == 403
    assert client.post(url, json={"approve": True}, headers=owner_headers).json()["status"] == (
        "approved"
    )
    db.expire_all()
    exp = db.get(Experiment, exp_id)
    assert exp and exp.status == "running" and "MATT never pays" in (exp.decision or "")


def test_no_bots_without_a_model_and_heartbeat_when_idle(
    client: TestClient, owner_headers: dict[str, str], seeded: None, settings: Settings, db: Session
) -> None:
    router = ModelRouter(settings, providers=[])
    autopilot.tick(db, router, force=True)
    assert not [t for t in db.query(Task).all() if t.input.get("workflow") == "skill_bot"]
    assert autopilot.get(db).last_tick_at is not None


def test_report_is_saved_even_when_the_ai_fails(
    client: TestClient, owner_headers: dict[str, str], seeded: None, settings: Settings, db: Session
) -> None:
    router = ModelRouter(settings, providers=[free(fail=True)])
    task = autopilot.tick(db, router, force=True)
    assert task is not None and task.input["workflow"] == "daily_report"
    drain(db, router)
    db.refresh(task)
    assert task.status == "succeeded"
    report = autopilot.status(db, router)["latest_report"]
    assert report and "AI recommendations unavailable" in report["content"]
    # The day has its report, so the next cycle moves on instead of retrying it.
    nxt = autopilot.tick(db, router, force=True)
    assert nxt is not None and nxt.input["workflow"] != "daily_report"


def test_old_30_minute_rows_move_to_15(db: Session) -> None:
    from app.models import Autopilot

    db.add(Autopilot(enabled=True, cities=["Mysuru"], categories=["gyms"], interval_minutes=30))
    db.commit()
    assert autopilot.get(db).interval_minutes == 15
