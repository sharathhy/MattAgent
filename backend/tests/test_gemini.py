from typing import Any

import httpx
import pytest

from app.core.config import Settings
from app.llm import providers
from app.llm.providers import GeminiProvider, ModelSpec, pick_gemini_model, suggested_model
from app.llm.router import ModelRouter
from tests.fakes import free, paid


def _resp(status: int, body: dict[str, Any], url: str) -> httpx.Response:
    return httpx.Response(status, json=body, request=httpx.Request("GET", url))


def test_pick_gemini_model_prefers_alias_then_newest_stable_flash() -> None:
    skip = GeminiProvider.SKIP
    assert pick_gemini_model(
        ["gemini-3-flash", "gemini-flash-latest"], ("gemini-flash-latest",), skip
    ) == ("gemini-flash-latest")
    ids = ["gemini-2.0-flash", "gemini-3-flash", "gemini-3-flash-preview", "gemini-3-pro",
           "gemini-3-flash-image", "text-embedding-004"]  # fmt: skip
    assert pick_gemini_model(ids, (), skip) == "gemini-3-flash"
    assert pick_gemini_model(["gemini-3-pro"], (), skip) is None


def test_retired_model_404_switches_to_current_model(monkeypatch: pytest.MonkeyPatch) -> None:
    spec = ModelSpec(provider="gemini", model="gemini-2.5-flash", tier="free", quality=3)
    gemini = GeminiProvider(spec, "https://g.example/v1beta/openai", "k")
    sent: list[str] = []

    def post(url: str, **kw: Any) -> httpx.Response:
        sent.append(kw["json"]["model"])
        if kw["json"]["model"] == "gemini-2.5-flash":
            return _resp(404, {"error": "not found"}, url)
        return _resp(200, {"choices": [{"message": {"content": "hi"}}],
                           "usage": {"prompt_tokens": 3, "completion_tokens": 1}}, url)  # fmt: skip

    def get(url: str, **kw: Any) -> httpx.Response:
        return _resp(200, {"data": [{"id": "models/gemini-flash-latest"}]}, url)

    monkeypatch.setattr(providers.httpx, "post", post)
    monkeypatch.setattr(providers.httpx, "get", get)
    assert gemini.complete("s", "p", 10).text == "hi"
    assert sent == ["gemini-2.5-flash", "gemini-flash-latest"]
    assert gemini.spec.model == "gemini-flash-latest"


def test_free_models_only_blocks_paid_and_premium(settings: Settings) -> None:
    assert settings.free_models_only
    settings.daily_ai_budget_inr = settings.monthly_ai_budget_inr = 1000
    settings.allow_premium_models = True
    premium = paid()
    object.__setattr__(premium.spec, "tier", "premium")
    assert not ModelRouter(settings, providers=[paid(), premium]).available
    assert ModelRouter(settings, providers=[free(), paid()]).available


def test_free_models_only_skips_anthropic_key(settings: Settings) -> None:
    settings.anthropic_api_key = "set"
    assert all(p.spec.provider != "anthropic" for p in ModelRouter(settings).providers)


def test_newest_full_flash_beats_lite_and_older() -> None:
    ids = ["gemini-3.5-flash-lite", "gemini-3.8-flash-lite-tts", "gemini-3.7-flash",
           "gemini-3.8-flash", "gemini-3.8-live", "gemini-2.5-flash"]  # fmt: skip
    assert pick_gemini_model(ids, (), GeminiProvider.SKIP) == "gemini-3.8-flash"


def test_follows_the_replacement_google_names_in_the_error() -> None:
    error = (
        'gemini HTTP 404: [{ "error": { "code": 404, "message": "This model '
        "models/gemini-2.5-flash is no longer available to new users. Please update your code "
        "to use models/gemini-3.8-flash for the latest features and improvements."
    )
    assert suggested_model(error, "gemini-2.5-flash") == "gemini-3.8-flash"
    assert suggested_model("HTTP 404: not found", "gemini-2.5-flash") is None
