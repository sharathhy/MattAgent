"""Google sign-in: real RS256 tokens signed by a test key stand in for Google's."""

import time
from collections.abc import Iterator
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings
from app.core.google import GoogleTokenError, GoogleTokenVerifier
from app.db.session import get_db
from app.main import create_app

CLIENT_ID = "test-client.apps.googleusercontent.com"
OWNER_EMAIL = "sharathhy65@gmail.com"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


class FakeKeys:
    def get_signing_key_from_jwt(self, token: str) -> jwt.PyJWK:
        return jwt.PyJWK.from_dict(
            {**jwt.algorithms.RSAAlgorithm.to_jwk(KEY.public_key(), as_dict=True), "alg": "RS256"}
        )


def token(key: Any = KEY, **overrides: Any) -> str:
    now = int(time.time())
    claims = {
        "iss": "https://accounts.google.com", "aud": CLIENT_ID, "sub": "123",
        "email": OWNER_EMAIL, "email_verified": True, "name": "Sharath",
        "iat": now, "exp": now + 300, **overrides,
    }  # fmt: skip
    return jwt.encode(claims, key, algorithm="RS256")


@pytest.fixture
def verifier() -> GoogleTokenVerifier:
    return GoogleTokenVerifier(CLIENT_ID, keys=FakeKeys())


@pytest.fixture
def gclient(
    settings: Settings, session_factory: sessionmaker[Session], verifier: GoogleTokenVerifier
) -> Iterator[TestClient]:
    settings = settings.model_copy(
        update={"google_client_id": CLIENT_ID, "owner_email": OWNER_EMAIL}
    )
    app = create_app(settings)
    app.state.google_verifier = verifier

    def _db() -> Iterator[Session]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app) as c:
        yield c


def test_verifier_accepts_valid_token(verifier: GoogleTokenVerifier) -> None:
    assert verifier.verify(token()).email == OWNER_EMAIL


@pytest.mark.parametrize(
    "bad",
    [
        {"aud": "someone-elses-app"},
        {"iss": "https://evil.example"},
        {"exp": int(time.time()) - 10},
        {"email_verified": False},
    ],
)
def test_verifier_rejects_bad_claims(verifier: GoogleTokenVerifier, bad: dict[str, Any]) -> None:
    with pytest.raises(GoogleTokenError):
        verifier.verify(token(**bad))


def test_verifier_rejects_forged_signature(verifier: GoogleTokenVerifier) -> None:
    with pytest.raises(GoogleTokenError):
        verifier.verify(token(key=OTHER_KEY))


def test_owner_email_becomes_owner_and_has_no_password(gclient: TestClient) -> None:
    status = gclient.get("/api/auth/status").json()
    assert status["google_client_id"] == CLIENT_ID
    r = gclient.post("/api/auth/google", json={"credential": token()})
    assert r.status_code == 200
    me = gclient.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {r.json()['access_token']}"}
    ).json()
    assert me["email"] == OWNER_EMAIL
    assert me["role"] == "owner"
    # A Google-only account cannot be entered with any password.
    bad = gclient.post("/api/auth/login", json={"email": OWNER_EMAIL, "password": "!"})
    assert bad.status_code == 401


def test_other_google_accounts_are_refused(gclient: TestClient) -> None:
    r = gclient.post("/api/auth/google", json={"credential": token(email="intruder@gmail.com")})
    assert r.status_code == 403
    assert gclient.get("/api/auth/status").json()["bootstrap_required"] is True


def test_owner_email_cannot_take_over_existing_install(gclient: TestClient) -> None:
    body = {"email": "first@example.com", "password": "correct-horse-battery"}
    assert gclient.post("/api/auth/bootstrap", json=body).status_code == 201
    r = gclient.post("/api/auth/google", json={"credential": token()})
    assert r.status_code == 403


def test_forged_token_rejected_by_endpoint(gclient: TestClient) -> None:
    r = gclient.post("/api/auth/google", json={"credential": token(key=OTHER_KEY)})
    assert r.status_code == 401


def test_google_disabled_without_client_id(client: TestClient) -> None:
    r = client.post("/api/auth/google", json={"credential": token()})
    assert r.status_code == 404
