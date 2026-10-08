from dataclasses import dataclass, field

from app.llm.providers import Completion, ModelSpec, ProviderError


@dataclass
class FakeProvider:
    spec: ModelSpec
    replies: list[str] = field(default_factory=lambda: ["ok"])
    fail: bool = False
    calls: list[tuple[str, str]] = field(default_factory=list)

    def complete(self, system: str, prompt: str, max_tokens: int) -> Completion:
        self.calls.append((system, prompt))
        if self.fail:
            raise ProviderError("boom")
        text = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        return Completion(text=text, prompt_tokens=100, completion_tokens=50, latency_ms=5)


def free(replies: list[str] | None = None, fail: bool = False) -> FakeProvider:
    return FakeProvider(ModelSpec("fake", "fake-free", "free", 3), replies or ["ok"], fail)


def paid(replies: list[str] | None = None) -> FakeProvider:
    spec = ModelSpec("fake", "fake-paid", "low", 4, usd_in_per_m=1.0, usd_out_per_m=2.0)
    return FakeProvider(spec, replies or ["paid ok"])
