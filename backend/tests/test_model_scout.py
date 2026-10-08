from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.llm import providers
from app.llm.providers import ChatModelProvider, ModelSpec, OpenRouterProvider, ProviderError
from app.llm.router import ModelRouter
from app.models import Approval
from app.services import model_scout

OPENROUTER_MODELS = [
    {"id": "openai/gpt-5", "pricing": {"prompt": "0.00001", "completion": "0.00003"}},
    {"id": "meta-llama/llama-3.3-70b-instruct:free", "pricing": {"prompt": "0", "completion": "0"},
     "context_length": 131072},
    {"id": "qwen/qwen3-8b:free", "pricing": {"prompt": "0", "completion": "0"}},
    {"id": "sneaky/paid-model:free", "pricing": {"prompt": "0.001", "completion": "0"}},
]  # fmt: skip


def _resp(body: dict[str, Any], url: str) -> httpx.Response:
    return httpx.Response(200, json=body, request=httpx.Request("GET", url))


def test_openrouter_only_ever_uses_free_models(monkeypatch: pytest.MonkeyPatch) -> None:
    spec = ModelSpec("openrouter", "", "free", 3)
    p = OpenRouterProvider(spec, "https://openrouter.ai/api/v1", "k")
    assert p.pick(OPENROUTER_MODELS) == "meta-llama/llama-3.3-70b-instruct:free"
    p.use_model("openai/gpt-5")

    def no_post(*a: Any, **k: Any) -> None:
        raise AssertionError("a paid model must never be called")

    monkeypatch.setattr(providers.httpx, "post", no_post)
    with pytest.raises(ProviderError, match="not free"):
        p.complete("s", "p", 10)


def test_chat_provider_picks_strongest_general_model() -> None:
    spec = ModelSpec("groq", "", "free", 3)
    p = ChatModelProvider(spec, "https://api.groq.com/openai/v1", "k")
    ids = ["whisper-large-v3", "llama-guard-4-12b", "llama-3.1-8b-instant", "qwen3-32b",
           "openai/gpt-oss-120b"]  # fmt: skip
    assert p.pick([{"id": i} for i in ids]) == "openai/gpt-oss-120b"
    p2 = ChatModelProvider(spec, "u", "k", preferred=("qwen3-32b",))
    assert p2.pick([{"id": i} for i in ids]) == "qwen3-32b"


def test_scan_switches_models_and_suggests_a_missing_key(
    monkeypatch: pytest.MonkeyPatch, settings: Settings, db: Session, owner_headers: dict[str, str]
) -> None:
    settings.gemini_api_key, settings.gemini_model = "g", "gemini-2.5-flash"
    settings.openrouter_api_key = "o"
    router = ModelRouter(settings)

    def get(url: str, **kw: Any) -> httpx.Response:
        if "openrouter" in url:
            return _resp({"data": OPENROUTER_MODELS}, url)
        return _resp(
            {"data": [{"id": "models/gemini-3.8-flash"}, {"id": "models/gemini-3.8-live"}]}, url
        )

    monkeypatch.setattr(providers.httpx, "get", get)
    found = {s["slug"]: s for s in model_scout.scan(db, router)}
    assert found["gemini"]["status"] == "ok" and found["gemini"]["model"] == "gemini-3.8-flash"
    assert router.provider("gemini").spec.model == "gemini-3.8-flash"  # type: ignore[union-attr]
    assert (
        found["openrouter"]["model"].endswith(":free") and found["openrouter"]["free_models"] == 2
    )
    assert found["groq"]["status"] == "not_connected"
    assert found["groq"]["suggested"] and not found["cerebras"]["suggested"]
    assert not db.scalars(select(Approval)).all()  # approvals are only for money


def test_scan_records_errors_without_failing(
    monkeypatch: pytest.MonkeyPatch, settings: Settings, db: Session
) -> None:
    settings.groq_api_key = "k"
    router = ModelRouter(settings)

    def down(url: str, **kw: Any) -> httpx.Response:
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(providers.httpx, "get", down)
    found = {s["slug"]: s for s in model_scout.scan(db, router)}
    assert found["groq"]["status"] == "error" and "offline" in found["groq"]["error"]
    assert not db.scalars(select(Approval)).all()


def test_scout_api_roles(
    client: TestClient, owner_headers: dict[str, str], viewer_headers: dict[str, str]
) -> None:
    rows = client.get("/api/models/free-sources", headers=viewer_headers).json()
    assert {r["slug"] for r in rows} >= {"gemini", "groq", "openrouter", "cerebras", "mistral"}
    assert client.post("/api/models/scout", headers=viewer_headers).status_code == 403
    assert client.post("/api/models/scout", headers=owner_headers).status_code == 200
