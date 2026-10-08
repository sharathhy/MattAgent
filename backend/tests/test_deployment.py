"""Single-service public deployments: setup code, SPA serving, provider database URLs."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.main import create_app
from tests.conftest import OWNER


def _client(settings: Settings, factory: sessionmaker[Session]) -> TestClient:
    app = create_app(settings)

    def _db() -> Iterator[Session]:
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app)


@pytest.fixture
def coded(settings: Settings, session_factory: sessionmaker[Session]) -> TestClient:
    return _client(
        settings.model_copy(update={"bootstrap_token": "open-sesame-42"}), session_factory
    )


def test_setup_code_required(coded: TestClient) -> None:
    assert coded.get("/api/auth/status").json()["setup_code_required"] is True
    assert coded.post("/api/auth/bootstrap", json=OWNER).status_code == 403
    wrong = coded.post("/api/auth/bootstrap", json={**OWNER, "setup_code": "guess"})
    assert wrong.status_code == 403
    ok = coded.post("/api/auth/bootstrap", json={**OWNER, "setup_code": "open-sesame-42"})
    assert ok.status_code == 201


def test_production_without_code_disables_web_bootstrap(
    session_factory: sessionmaker[Session],
) -> None:
    prod = Settings(env="production", secret_key="x" * 40, database_url="postgresql://u:p@h/db")
    client = _client(prod, session_factory)
    assert client.get("/api/auth/status").json()["web_bootstrap_enabled"] is False
    assert client.post("/api/auth/bootstrap", json=OWNER).status_code == 403


@pytest.mark.parametrize(
    "url", ["postgres://u:p@h:5432/db", "postgresql://u:p@h:5432/db"]
)  # fmt: skip
def test_provider_database_urls_get_psycopg_driver(url: str) -> None:
    assert Settings(database_url=url).database_url == "postgresql+psycopg://u:p@h:5432/db"


@pytest.fixture
def spa(tmp_path: Path, settings: Settings, session_factory: sessionmaker[Session]) -> TestClient:
    web = tmp_path / "web"
    (web / "assets").mkdir(parents=True)
    (web / "index.html").write_text("<div id=root></div>")
    (web / "assets" / "app.js").write_text("console.log(1)")
    (tmp_path / "secret.txt").write_text("nope")
    return _client(settings.model_copy(update={"static_dir": str(web)}), session_factory)


def test_spa_serves_index_for_client_routes(spa: TestClient) -> None:
    r = spa.get("/agents/ceo")
    assert r.status_code == 200
    assert "root" in r.text
    assert "default-src 'self'" in r.headers["Content-Security-Policy"]
    assert spa.get("/assets/app.js").text == "console.log(1)"


def test_spa_does_not_shadow_api_or_escape_root(spa: TestClient) -> None:
    assert spa.get("/api/nope").status_code == 404
    assert spa.get("/api/health").json()["database"] == "ok"
    assert "nope" not in spa.get("/..%2Fsecret.txt").text


def test_web_pages_let_the_google_popup_report_back(spa: TestClient) -> None:
    page = spa.get("/command-center")
    assert page.headers["Cross-Origin-Opener-Policy"] == "same-origin-allow-popups"
    assert "Cross-Origin-Opener-Policy" not in spa.get("/api/health").headers
