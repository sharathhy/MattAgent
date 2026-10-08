"""Model providers behind one interface. Each returns text plus token usage."""

import re
import time
from dataclasses import dataclass, replace
from typing import Any, Protocol

import anthropic
import httpx


@dataclass(frozen=True)
class Completion:
    text: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: int


class ProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class ModelSpec:
    """One routable model. Prices are USD per 1M tokens (0 for free tiers and local models)."""

    provider: str
    model: str
    tier: str  # local | free | low | premium
    quality: int  # 1 (basic) .. 5 (best)
    usd_in_per_m: float = 0.0
    usd_out_per_m: float = 0.0
    rate_limit: str = ""
    use_cases: tuple[str, ...] = ()

    @property
    def paid(self) -> bool:
        return self.usd_in_per_m > 0 or self.usd_out_per_m > 0

    def cost_usd(self, prompt_tokens: int, completion_tokens: int) -> float:
        return (prompt_tokens * self.usd_in_per_m + completion_tokens * self.usd_out_per_m) / 1e6


class Provider(Protocol):
    spec: ModelSpec

    def complete(self, system: str, prompt: str, max_tokens: int) -> Completion: ...


class OpenAICompatibleProvider:
    """Gemini, Groq and Ollama all expose the OpenAI chat-completions wire format."""

    def __init__(self, spec: ModelSpec, base_url: str, api_key: str | None, timeout: float = 90):
        self.spec = spec
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def complete(self, system: str, prompt: str, max_tokens: int) -> Completion:
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        body: dict[str, Any] = {
            "model": self.spec.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": max_tokens,
        }
        start = time.perf_counter()
        try:
            r = httpx.post(
                f"{self.base_url}/chat/completions",
                json=body,
                headers=headers,
                timeout=self.timeout,
            )
        except httpx.HTTPError as exc:
            raise ProviderError(f"{self.spec.provider}: {exc}") from exc
        if r.status_code >= 400:
            raise ProviderError(f"{self.spec.provider} HTTP {r.status_code}: {r.text[:300]}")
        data = r.json()
        try:
            text = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError(f"{self.spec.provider}: unexpected response shape") from exc
        usage = data.get("usage") or {}
        return Completion(
            text=text,
            prompt_tokens=int(usage.get("prompt_tokens", 0)),
            completion_tokens=int(usage.get("completion_tokens", 0)),
            latency_ms=int((time.perf_counter() - start) * 1000),
        )


class GeminiProvider(OpenAICompatibleProvider):
    """Gemini through its OpenAI-compatible endpoint, free tier.

    Google retires model names over time. If the configured name returns 404, the provider asks
    the API which models this key can use, switches to the newest general "flash" model, and
    retries once, so a retired name never stops MATT.
    """

    PREFERRED = ("gemini-flash-latest", "gemini-flash-lite-latest")
    SKIP = ("image", "tts", "audio", "live", "embedding", "exp", "thinking", "vision", "pro")

    def complete(self, system: str, prompt: str, max_tokens: int) -> Completion:
        try:
            return super().complete(system, prompt, max_tokens)
        except ProviderError as exc:
            if "HTTP 404" not in str(exc):
                raise
            # Google's 404 usually names the replacement ("Please ... use models/<name>").
            current = suggested_model(str(exc), self.spec.model) or self.discover_model()
            if current is None or current == self.spec.model:
                raise
            self.spec = replace(self.spec, model=current)
            return super().complete(system, prompt, max_tokens)

    def discover_model(self) -> str | None:
        try:
            r = httpx.get(
                f"{self.base_url}/models",
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=30,
            )
            r.raise_for_status()
            ids = [str(m.get("id", "")).removeprefix("models/") for m in r.json().get("data", [])]
        except (httpx.HTTPError, ValueError, AttributeError):
            return None
        return pick_gemini_model(ids, self.PREFERRED, self.SKIP)


def suggested_model(error: str, current: str) -> str | None:
    """The replacement model a Gemini error message recommends, if it names one."""
    for match in re.findall(r"use (?:models/)?(gemini-[\w.-]*flash[\w.-]*)", error):
        name = str(match).rstrip(".")
        if name != current and not any(word in name for word in GeminiProvider.SKIP):
            return name
    return None


def _version(model_id: str) -> tuple[float, ...]:
    return tuple(float(n) for n in re.findall(r"\d+(?:\.\d+)?", model_id)[:1]) or (0.0,)


def pick_gemini_model(
    ids: list[str], preferred: tuple[str, ...], skip: tuple[str, ...]
) -> str | None:
    for name in preferred:
        if name in ids:
            return name
    flash = [i for i in ids if "flash" in i and not any(word in i for word in skip)]
    stable = [i for i in flash if "preview" not in i] or flash
    # Newest version first; the full Flash model before Flash-Lite of the same version.
    return max(stable, key=lambda i: (_version(i), "lite" not in i), default=None)


class AnthropicProvider:
    """Claude via the official SDK. Premium tier: only used when explicitly allowed."""

    def __init__(self, spec: ModelSpec, api_key: str):
        self.spec = spec
        self.client = anthropic.Anthropic(api_key=api_key, max_retries=1)

    def complete(self, system: str, prompt: str, max_tokens: int) -> Completion:
        start = time.perf_counter()
        try:
            # Server-side refusal fallback is on by default for current Claude models.
            response = self.client.beta.messages.create(
                model=self.spec.model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": prompt}],
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
        except anthropic.APIError as exc:
            raise ProviderError(f"anthropic: {exc}") from exc
        if response.stop_reason == "refusal":
            raise ProviderError("anthropic: request declined by safety classifiers")
        text = "".join(b.text for b in response.content if b.type == "text")
        return Completion(
            text=text,
            prompt_tokens=response.usage.input_tokens,
            completion_tokens=response.usage.output_tokens,
            latency_ms=int((time.perf_counter() - start) * 1000),
        )
