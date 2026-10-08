import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.usefixtures("seeded")


def test_agents_require_auth(client: TestClient) -> None:
    assert client.get("/api/agents").status_code == 401


def test_summary(client: TestClient, viewer_headers: dict[str, str]) -> None:
    s = client.get("/api/agents/summary", headers=viewer_headers).json()
    assert s["total"] == 120
    assert s["by_kind"] == {"ceo": 1, "executive": 9, "skill": 100, "meta": 10}
    assert s["by_status"] == {"designed": 120}


def test_list_filters(client: TestClient, viewer_headers: dict[str, str]) -> None:
    sales = client.get("/api/agents", params={"department": "sales"}, headers=viewer_headers).json()
    assert {a["slug"] for a in sales} >= {"cro", "lead-qualifier"}
    found = client.get("/api/agents", params={"q": "thumbnail"}, headers=viewer_headers).json()
    assert [a["slug"] for a in found] == ["thumbnail-agent"]
    follow = next(a for a in sales if a["slug"] == "follow-up-agent")
    assert follow["requires_approval"] is True


def test_hierarchy(client: TestClient, viewer_headers: dict[str, str]) -> None:
    roots = client.get("/api/agents/hierarchy", headers=viewer_headers).json()
    assert [r["slug"] for r in roots] == ["ceo"]
    execs = {c["slug"]: c for c in roots[0]["children"]}
    assert {"coo", "cfo", "cto", "cmo", "chro"} <= set(execs)
    assert len(execs["chro"]["children"]) == 10


def test_detail_has_no_fabricated_metrics(
    client: TestClient, viewer_headers: dict[str, str]
) -> None:
    a = client.get("/api/agents/lead-qualifier", headers=viewer_headers).json()
    assert a["parent_slug"] == "cro"
    assert a["dependencies"] == ["lead-researcher"]
    assert a["performance_score"] is None
    assert a["success_rate"] is None
    assert a["tasks_completed"] == 0
    assert a["versions"][0]["version"] == "1.0.0"
    assert client.get("/api/agents/nope", headers=viewer_headers).status_code == 404


def test_status_transition(client: TestClient, admin_headers: dict[str, str]) -> None:
    r = client.patch(
        "/api/agents/seo-agent/status", json={"status": "built"}, headers=admin_headers
    )
    assert r.status_code == 200
    assert r.json()["status"] == "built"
    skip = client.patch(
        "/api/agents/seo-agent/status", json={"status": "deployed"}, headers=admin_headers
    )
    assert skip.status_code == 409


def test_viewer_cannot_change_status(client: TestClient, viewer_headers: dict[str, str]) -> None:
    r = client.patch(
        "/api/agents/seo-agent/status", json={"status": "built"}, headers=viewer_headers
    )
    assert r.status_code == 403


def test_reseed_preserves_owner_changes(
    client: TestClient, admin_headers: dict[str, str], db
) -> None:  # type: ignore[no-untyped-def]
    from app.services import registry

    client.patch("/api/agents/seo-agent/status", json={"status": "built"}, headers=admin_headers)
    result = registry.seed_registry(db)
    assert result.created == 0
    assert result.existing == 120
    assert client.get("/api/agents/seo-agent", headers=admin_headers).json()["status"] == "built"
