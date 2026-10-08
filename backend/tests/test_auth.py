from fastapi.testclient import TestClient

from tests.conftest import OWNER, login


def test_bootstrap_only_once(client: TestClient) -> None:
    assert client.get("/api/auth/status").json() == {"bootstrap_required": True}
    r = client.post("/api/auth/bootstrap", json=OWNER)
    assert r.status_code == 201
    assert r.json()["role"] == "owner"
    assert "password" not in r.text
    assert client.get("/api/auth/status").json() == {"bootstrap_required": False}
    again = client.post("/api/auth/bootstrap", json={**OWNER, "email": "other@example.com"})
    assert again.status_code == 409


def test_weak_password_rejected(client: TestClient) -> None:
    r = client.post("/api/auth/bootstrap", json={**OWNER, "password": "short"})
    assert r.status_code == 422


def test_login_and_me(client: TestClient, owner_headers: dict[str, str]) -> None:
    me = client.get("/api/auth/me", headers=owner_headers)
    assert me.status_code == 200
    assert me.json()["email"] == OWNER["email"]


def test_login_is_case_insensitive_on_email(
    client: TestClient, owner_headers: dict[str, str]
) -> None:
    login(client, OWNER["email"].upper(), OWNER["password"])


def test_bad_credentials(client: TestClient, owner_headers: dict[str, str]) -> None:
    r = client.post("/api/auth/login", json={"email": OWNER["email"], "password": "wrong-password"})
    assert r.status_code == 401


def test_invalid_token_rejected(client: TestClient) -> None:
    r = client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-token"})
    assert r.status_code == 401
    assert client.get("/api/auth/me").status_code == 401


def test_only_owner_creates_users(client: TestClient, viewer_headers: dict[str, str]) -> None:
    body = {"email": "x@example.com", "password": "another-password", "role": "admin"}
    assert client.post("/api/auth/users", json=body, headers=viewer_headers).status_code == 403


def test_cannot_create_second_owner(client: TestClient, owner_headers: dict[str, str]) -> None:
    body = {"email": "x@example.com", "password": "another-password", "role": "owner"}
    assert client.post("/api/auth/users", json=body, headers=owner_headers).status_code == 400


def test_login_rate_limited(client: TestClient, owner_headers: dict[str, str]) -> None:
    bad = {"email": OWNER["email"], "password": "wrong-password"}
    codes = [client.post("/api/auth/login", json=bad).status_code for _ in range(12)]
    assert 429 in codes
