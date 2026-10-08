import base64
import json
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.llm.providers import ModelSpec
from app.llm.router import ModelRouter
from app.models import ChangeRequest, ModelUsage
from app.services import changes, github, tasks
from tests.fakes import FakeProvider, free

BASE = "claude/matt-foundation-cnz4ei"
FILES = {
    "frontend/src/pages/SettingsPage.tsx": "export const A = 1;\n",
    "backend/app/main.py": "app = 1\n",
    ".github/workflows/ci.yml": "on: push\n",
}


class FakeGitHub:
    """Just enough of the GitHub REST API, recording every write."""

    def __init__(self) -> None:
        self.writes: list[tuple[str, str, Any]] = []

    def __call__(self, method: str, url: str, **kw: Any) -> httpx.Response:
        path = url.split("/repos/sharathhy/MattAgent", 1)[1]
        req = httpx.Request(method, url)
        if method != "GET":
            self.writes.append((method, path, kw.get("json")))
        if path == f"/git/ref/heads/{BASE}":
            body: Any = {"object": {"sha": "base123"}}
        elif path.startswith("/git/trees/"):
            body = {"tree": [{"path": p, "type": "blob"} for p in FILES]}
        elif method == "GET" and path.startswith("/contents/"):
            name = path.removeprefix("/contents/")
            if name not in FILES:
                return httpx.Response(404, json={}, request=req)
            content = base64.b64encode(FILES[name].encode()).decode()
            body = {"type": "file", "content": content, "sha": f"sha-{name}"}
        elif path == "/pulls":
            body = {"html_url": "https://github.com/sharathhy/MattAgent/pull/42"}
        else:
            body = {}
        return httpx.Response(200, json=body, request=req)


@pytest.fixture
def gh(monkeypatch: pytest.MonkeyPatch, settings: Settings) -> FakeGitHub:
    fake = FakeGitHub()
    monkeypatch.setattr(github.httpx, "request", fake)
    settings.github_token = "test-token"
    return fake


DRAFT = (
    "PLAN: Add a dark mode note to Settings.\n"
    "=== FILE: frontend/src/pages/SettingsPage.tsx ===\nexport const A = 2;\n=== END FILE ==="
)


def _router(client: TestClient, provider: FakeProvider) -> ModelRouter:
    router = ModelRouter(client.app.state.model_router.settings, providers=[provider])  # type: ignore[attr-defined]
    client.app.state.model_router = router  # type: ignore[attr-defined]
    return router


def drain(db: Session, router: ModelRouter) -> None:
    while tasks.process_next(db, router):
        pass


def test_owner_change_is_drafted_approved_then_opened_as_pr(
    client: TestClient, owner_headers: dict[str, str], admin_headers: dict[str, str],
    seeded: None, gh: FakeGitHub, db: Session,
) -> None:  # fmt: skip
    router = _router(client, free(["frontend/src/pages/SettingsPage.tsx", DRAFT]))
    body = {"request": "Add a dark mode note to the settings page"}
    assert client.post("/api/changes", json=body, headers=admin_headers).status_code == 403
    r = client.post("/api/changes", json=body, headers=owner_headers)
    assert r.status_code == 201 and r.json()["status"] == "drafting"
    drain(db, router)
    change = client.get("/api/changes", headers=owner_headers).json()[0]
    assert change["status"] == "awaiting_approval"
    assert change["files"] == ["frontend/src/pages/SettingsPage.tsx"]
    assert "-export const A = 1;" in change["diff"] and "+export const A = 2;" in change["diff"]
    assert not gh.writes  # nothing written to GitHub before approval

    approval = client.get("/api/approvals?status=pending", headers=owner_headers).json()[0]
    assert approval["kind"] == "code_change" and approval["risk_level"] == "high"
    url = f"/api/approvals/{approval['id']}/decide"
    assert client.post(url, json={"approve": True}, headers=admin_headers).status_code == 403
    client.post(url, json={"approve": True}, headers=owner_headers)
    drain(db, router)
    change = client.get("/api/changes", headers=owner_headers).json()[0]
    assert change["status"] == "pr_opened" and change["pr_url"].endswith("/pull/42")
    refs = [w for w in gh.writes if w[1] == "/git/refs"]
    assert (
        refs
        and refs[0][2]["sha"] == "base123"
        and refs[0][2]["ref"].startswith("refs/heads/matt/change-1-")
    )
    puts = [w for w in gh.writes if w[0] == "PUT"]
    assert [p[1] for p in puts] == ["/contents/frontend/src/pages/SettingsPage.tsx"]
    assert puts[0][2]["branch"] != BASE  # never the deploy branch
    pr = next(w for w in gh.writes if w[1] == "/pulls")[2]
    assert pr["base"] == BASE and "never merges" in pr["body"]
    assert not any("merge" in w[1] for w in gh.writes)


def test_rejected_change_never_touches_github(
    client: TestClient, owner_headers: dict[str, str], seeded: None, gh: FakeGitHub, db: Session
) -> None:
    router = _router(client, free(["frontend/src/pages/SettingsPage.tsx", DRAFT]))
    client.post("/api/changes", json={"request": "Add a dark mode note"}, headers=owner_headers)
    drain(db, router)
    approval = client.get("/api/approvals?status=pending", headers=owner_headers).json()[0]
    client.post(f"/api/approvals/{approval['id']}/decide", json={"approve": False},
                headers=owner_headers)  # fmt: skip
    drain(db, router)
    assert db.query(ChangeRequest).one().status == "rejected"
    assert not gh.writes


def test_protected_files_and_money_rule(
    client: TestClient, owner_headers: dict[str, str], seeded: None, gh: FakeGitHub, db: Session
) -> None:
    evil = "PLAN: x\n=== FILE: .github/workflows/ci.yml ===\non: never\n=== END FILE ==="
    router = _router(client, free(["frontend/src/pages/SettingsPage.tsx", evil]))
    client.post("/api/changes", json={"request": "Speed up the CI pipeline"}, headers=owner_headers)
    drain(db, router)
    row = db.query(ChangeRequest).one()
    assert row.status == "failed" and "protected file" in (row.error or "")
    assert not changes.allowed_path("render.yaml") and not changes.allowed_path("backend/.env")
    r = client.post("/api/changes", json={"request": "Make MATT withdraw money daily"},
                    headers=owner_headers)  # fmt: skip
    assert r.status_code == 403


def test_without_token_it_says_what_to_add(
    client: TestClient, owner_headers: dict[str, str], seeded: None, db: Session
) -> None:
    router = _router(client, free(["x"]))
    client.post("/api/changes", json={"request": "Add a dark mode note"}, headers=owner_headers)
    drain(db, router)
    row = db.query(ChangeRequest).one()
    assert row.status == "failed" and "MATT_GITHUB_TOKEN" in (row.error or "")


def test_voice_command_creates_a_change_request(
    client: TestClient, owner_headers: dict[str, str], viewer_headers: dict[str, str], seeded: None
) -> None:
    r = client.post("/api/command", json={"text": "Hey Matt, change your code to add a clock"},
                    headers=owner_headers).json()  # fmt: skip
    assert r["intent"] == "code_change" and "approve" in r["reply"]
    r2 = client.post("/api/command", json={"text": "change your ui to be red"},
                     headers=viewer_headers)  # fmt: skip
    assert r2.status_code == 403
    assert json.dumps(client.get("/api/changes", headers=owner_headers).json()).count('"id"') == 1


def _claude(monkeypatch: pytest.MonkeyPatch, replies: list[str]) -> FakeProvider:
    spec = ModelSpec("anthropic", "claude-test", "premium", 5, usd_in_per_m=4.0, usd_out_per_m=20.0)
    fake = FakeProvider(spec, replies)
    monkeypatch.setattr(changes, "AnthropicProvider", lambda _spec, _key: fake)
    return fake


def test_claude_drafts_code_changes_only_within_the_owner_cap(
    client: TestClient, owner_headers: dict[str, str], seeded: None, gh: FakeGitHub,
    db: Session, settings: Settings, monkeypatch: pytest.MonkeyPatch,
) -> None:  # fmt: skip
    claude = _claude(monkeypatch, ["frontend/src/pages/SettingsPage.tsx", DRAFT])
    business = free(["frontend/src/pages/SettingsPage.tsx", DRAFT])
    router = _router(client, business)
    status = client.get("/api/changes/config", headers=owner_headers).json()["code_ai"]
    assert status["provider"] == "free"  # no key and no cap: Claude stays off

    settings.anthropic_api_key = "sk-test"
    settings.code_ai_monthly_budget_inr = 500
    assert settings.free_models_only  # the business lock stays on
    client.post("/api/changes", json={"request": "Add a dark mode note"}, headers=owner_headers)
    drain(db, router)
    assert len(claude.calls) == 2 and not business.calls
    change = client.get("/api/changes", headers=owner_headers).json()[0]
    assert change["status"] == "awaiting_approval" and change["cost_inr"] > 0
    status = client.get("/api/changes/config", headers=owner_headers).json()["code_ai"]
    assert status["provider"] == "claude" and status["monthly_cap_inr"] == 500
    assert status["spent_30d_inr"] == pytest.approx(change["cost_inr"])

    # Business work never reaches Claude, even with the key set.
    assert not any(p.spec.provider == "anthropic" for p in ModelRouter(settings).providers)


def test_claude_falls_back_to_free_model_at_the_cap(
    client: TestClient, owner_headers: dict[str, str], seeded: None, gh: FakeGitHub,
    db: Session, settings: Settings, monkeypatch: pytest.MonkeyPatch,
) -> None:  # fmt: skip
    claude = _claude(monkeypatch, ["x"])
    fallback = free(["frontend/src/pages/SettingsPage.tsx", DRAFT])
    router = _router(client, fallback)
    settings.anthropic_api_key = "sk-test"
    settings.code_ai_monthly_budget_inr = 0.0001  # spent after one call
    db.add(ModelUsage(provider="anthropic", model="claude-test", cost_inr=1,
                      success=True))  # fmt: skip
    db.commit()
    client.post("/api/changes", json={"request": "Add a dark mode note"}, headers=owner_headers)
    drain(db, router)
    assert not claude.calls and len(fallback.calls) == 2
    assert db.query(ChangeRequest).one().status == "awaiting_approval"
