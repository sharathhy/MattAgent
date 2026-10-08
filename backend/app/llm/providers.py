"""Model providers behind one interface. Each returns text plus token usage."""

import time
from dataclasses import dataclass
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
