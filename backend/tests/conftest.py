from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings
from app.db.base import Base
from app.db.session import build_engine, get_db
from app.main import create_app
from app.services import registry

OWNER = {"email": "owner@example.com", "password": "correct-horse-battery", "full_name": "Owner"}


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(env="test", database_url=f"sqlite:///{tmp_path / 'test.db'}", log_json=False)


@pytest.fixture
def session_factory(settings: Settings) -> Iterator[sessionmaker[Session]]:
    engine = build_engine(settings.database_url)
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, expire_on_commit=False)
    engine.dispose()


@pytest.fixture
def db(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    with session_factory() as session:
        yield session


@pytest.fixture
def client(settings: Settings, session_factory: sessionmaker[Session]) -> Iterator[TestClient]:
    app = create_app(settings)

    def _db() -> Iterator[Session]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app) as c:
        yield c


@pytest.fixture
def seeded(db: Session) -> None:
    registry.seed_registry(db)


def login(client: TestClient, email: str, password: str) -> dict[str, str]:
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def owner_headers(client: TestClient) -> dict[str, str]:
    assert client.post("/api/auth/bootstrap", json=OWNER).status_code == 201
    return login(client, OWNER["email"], OWNER["password"])


@pytest.fixture
def viewer_headers(client: TestClient, owner_headers: dict[str, str]) -> dict[str, str]:
    body = {"email": "viewer@example.com", "password": "viewer-password-1", "role": "viewer"}
    assert client.post("/api/auth/users", json=body, headers=owner_headers).status_code == 201
    return login(client, body["email"], body["password"])


@pytest.fixture
def admin_headers(client: TestClient, owner_headers: dict[str, str]) -> dict[str, str]:
    body = {"email": "admin@example.com", "password": "admin-password-12", "role": "admin"}
    assert client.post("/api/auth/users", json=body, headers=owner_headers).status_code == 201
    return login(client, body["email"], body["password"])
