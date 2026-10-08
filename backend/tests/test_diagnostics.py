from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.llm.router import ModelRouter
from app.models import ModelUsage
from app.services import autopilot, diagnostics
from tests.fakes import free


def test_health_panel_explains_what_is_wrong(
    client: TestClient, owner_headers: dict[str, str], viewer_headers: dict[str, str],
    seeded: None, settings: Settings, db: Session,
) -> None:  # fmt: skip
    assert client.get("/api/diagnostics", headers=viewer_headers).status_code == 403
    settings.worker_enabled = True
    router = ModelRouter(settings, providers=[])
    report = diagnostics.report(db, router)
    texts = " ".join(p["text"] for p in report["problems"])
    assert not report["healthy"]
    assert "hasn't checked in yet" in texts and "No free AI model" in texts

    router = ModelRouter(settings, providers=[free()])
    row = autopilot.get(db)
    row.last_tick_at = datetime.now(UTC) - timedelta(seconds=20)
    db.add(ModelUsage(provider="fake", model="fake-free", success=False,
                      error="fake HTTP 429: quota exceeded"))  # fmt: skip
    db.commit()
    report = diagnostics.report(db, router)
    assert report["worker"]["last_heartbeat_at"] is not None
    fake = next(p for p in report["problems"] if p["text"].startswith("fake:"))
    assert "429" in fake["text"] and "resets by itself" in fake["fix"]


def test_ai_test_pings_each_model(
    client: TestClient, owner_headers: dict[str, str], seeded: None, settings: Settings
) -> None:
    client.app.state.model_router = ModelRouter(settings, providers=[free(["OK"])])  # type: ignore[attr-defined]
    r = client.post("/api/diagnostics/test-ai", headers=owner_headers).json()
    assert r == [{"provider": "fake", "model": "fake-free", "ok": True, "reply": "OK",
                  "latency_ms": 5}]  # fmt: skip
    client.app.state.model_router = ModelRouter(settings, providers=[free(fail=True)])  # type: ignore[attr-defined]
    r = client.post("/api/diagnostics/test-ai", headers=owner_headers).json()
    assert r[0]["ok"] is False and "boom" in r[0]["error"]
