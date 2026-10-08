"""Permission boundaries: no silent escalation, everything audited."""

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.usefixtures("seeded")


def test_admin_cannot_grant_permissions(client: TestClient, admin_headers: dict[str, str]) -> None:
    body = {"permissions": ["read", "financial"], "reason": "try escalation"}
    r = client.put("/api/agents/web-researcher/permissions", json=body, headers=admin_headers)
    assert r.status_code == 403


def test_owner_permission_change_is_versioned_and_audited(
    client: TestClient, owner_headers: dict[str, str]
) -> None:
    body = {"permissions": ["read", "write", "external_action"], "reason": "pilot outreach"}
    r = client.put("/api/agents/sales-copywriter/permissions", json=body, headers=owner_headers)
    assert r.status_code == 200
    agent = r.json()
    assert agent["version"] == "1.0.1"
    assert agent["requires_approval"] is True
    assert "external_action" in agent["versions"][-1]["change_summary"]

    logs = client.get(
        "/api/audit-logs", params={"action": "agent.permissions_changed"}, headers=owner_headers
    ).json()
    assert logs[0]["target_id"] == "sales-copywriter"
    assert logs[0]["details"]["high_risk_granted"] == ["external_action"]
    assert logs[0]["request_id"]


def test_unknown_permission_rejected(client: TestClient, owner_headers: dict[str, str]) -> None:
    body = {"permissions": ["superuser"], "reason": "nope"}
    r = client.put("/api/agents/web-researcher/permissions", json=body, headers=owner_headers)
    assert r.status_code == 422


def test_viewer_cannot_read_audit_log(client: TestClient, viewer_headers: dict[str, str]) -> None:
    assert client.get("/api/audit-logs", headers=viewer_headers).status_code == 403


def test_security_headers_and_request_id(client: TestClient) -> None:
    r = client.get("/api/health", headers={"X-Request-ID": "abc-123"})
    assert r.json()["status"] == "ok"
    assert r.headers["X-Request-ID"] == "abc-123"
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"


def test_malformed_request_id_replaced(client: TestClient) -> None:
    r = client.get("/api/health", headers={"X-Request-ID": "bad\nvalue"})
    assert r.headers["X-Request-ID"] != "bad\nvalue"


def test_tampered_token_rejected(client: TestClient, owner_headers: dict[str, str]) -> None:
    token = owner_headers["Authorization"]
    r = client.get("/api/auth/me", headers={"Authorization": token[:-2] + "xx"})
    assert r.status_code == 401
