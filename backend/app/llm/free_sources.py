"""Curated free-tier AI services MATT can use, ranked by how much free work they allow.

This is data for the Free Model Scout and the model router. Each entry is a service with a
genuine no-card free tier and an OpenAI-compatible API. MATT cannot sign up or create keys on
its own: the owner adds a key as an environment variable, and the scout asks for one in
Approvals when a useful service is not connected yet. Limits change often; they are shown as
ESTIMATES and the scout checks each connected service directly.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class FreeSource:
    slug: str
    name: str
    env_var: str
    base_url: str
    signup_url: str
    free_limits: str  # ESTIMATE, as published by the provider
    note: str = ""
    #: Whether the scout asks the owner to connect it (False for caveats like data training).
    recommend: bool = True
    preferred: tuple[str, ...] = ()


FREE_SOURCES: tuple[FreeSource, ...] = (
    FreeSource(
        "gemini", "Google Gemini (AI Studio)", "MATT_GEMINI_API_KEY",
        "https://generativelanguage.googleapis.com/v1beta/openai",
        "https://aistudio.google.com/apikey",
        "Free tier with per-minute and per-day caps (see AI Studio). Keep billing off.",
    ),
    FreeSource(
        "groq", "Groq", "MATT_GROQ_API_KEY", "https://api.groq.com/openai/v1",
        "https://console.groq.com/keys", "About 30 requests a minute and 1,000 a day.",
        preferred=("llama-3.3-70b-versatile", "openai/gpt-oss-120b"),
    ),
    FreeSource(
        "openrouter", "OpenRouter (free models only)", "MATT_OPENROUTER_API_KEY",
        "https://openrouter.ai/api/v1", "https://openrouter.ai/settings/keys",
        "20 requests a minute and 50 a day on models ending in ':free'.",
        note="MATT only calls ':free' models through this key and refuses any other.",
    ),
    FreeSource(
        "cerebras", "Cerebras", "MATT_CEREBRAS_API_KEY", "https://api.cerebras.ai/v1",
        "https://cloud.cerebras.ai", "About 30 requests a minute and 1M tokens a day.",
    ),
    FreeSource(
        "mistral", "Mistral (Experiment plan)", "MATT_MISTRAL_API_KEY",
        "https://api.mistral.ai/v1", "https://console.mistral.ai/api-keys",
        "Free Experiment plan with generous monthly tokens.",
        note="The free plan requires letting Mistral train on your prompts, so MATT does not "
        "ask for it; add it only if you accept that.",
        recommend=False, preferred=("mistral-small-latest",),
    ),
)  # fmt: skip

BY_SLUG = {s.slug: s for s in FREE_SOURCES}
