"""Free-first model router.

Order: local models → free API tiers → low-cost → premium. Paid usage is counted against daily
and monthly INR budgets; at the limit the router refuses and the caller asks the owner. MATT
never assumes unlimited free tokens: free tiers are rate limited, so failures fall through to
the next candidate.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.llm.free_sources import FREE_SOURCES
from app.llm.providers import (
    AnthropicProvider,
    ChatModelProvider,
    Completion,
    GeminiProvider,
    ModelSpec,
    OpenAICompatibleProvider,
    OpenRouterProvider,
    Provider,
    ProviderError,
)
from app.models import ModelUsage

log = logging.getLogger(__name__)

TIER_ORDER = {"local": 0, "free": 1, "low": 2, "premium": 3}
FREE_TIERS = frozenset({"local", "free"})


class NoModelAvailable(RuntimeError):
    """No configured model can take this request (none configured, all failed, or quality)."""


class BudgetExceeded(RuntimeError):
    pass


@dataclass(frozen=True)
class RoutedCompletion:
    completion: Completion
    spec: ModelSpec
    cost_inr: Decimal


def build_providers(settings: Settings) -> list[Provider]:
    providers: list[Provider] = []
    if settings.ollama_url:
        providers.append(
            OpenAICompatibleProvider(
                ModelSpec("ollama", settings.ollama_model, "local", 2, use_cases=("drafts",)),
                f"{settings.ollama_url.rstrip('/')}/v1",
                None,
            )
        )
    for source in FREE_SOURCES:
        key = getattr(settings, f"{source.slug}_api_key")
        if not key:
            continue
        model = getattr(settings, f"{source.slug}_model")
        spec = ModelSpec(source.slug, model, "free", 3, rate_limit=source.free_limits,
                         use_cases=("research", "writing"))  # fmt: skip
        if source.slug == "gemini":
            providers.append(GeminiProvider(spec, source.base_url, key))
        elif source.slug == "openrouter":
            providers.append(OpenRouterProvider(spec, source.base_url, key))
        else:
            providers.append(ChatModelProvider(spec, source.base_url, key, source.preferred))
    if settings.anthropic_api_key and not settings.free_models_only:
        providers.append(
            AnthropicProvider(
                ModelSpec(
                    "anthropic",
                    settings.anthropic_model,
                    "premium",
                    5,
                    4.0,
                    20.0,
                    use_cases=("critical reasoning", "architecture"),
                ),
                settings.anthropic_api_key,
            )
        )
    return providers


class ModelRouter:
    def __init__(self, settings: Settings, providers: list[Provider] | None = None) -> None:
        self.settings = settings
        self.providers = sorted(
            build_providers(settings) if providers is None else providers,
            key=lambda p: (TIER_ORDER[p.spec.tier], -p.spec.quality),
        )

    @property
    def available(self) -> bool:
        return any(self._eligible(p, 1) for p in self.providers)

    def provider(self, slug: str) -> Provider | None:
        return next((p for p in self.providers if p.spec.provider == slug), None)

    def catalog(self) -> list[ModelSpec]:
        return [p.spec for p in self.providers]

    def allowed(self, spec: ModelSpec) -> bool:
        """Whether settings let MATT call this model at all (free-only lock, premium opt-in)."""
        if self.settings.free_models_only and (spec.paid or spec.tier not in FREE_TIERS):
            return False
        return spec.tier != "premium" or self.settings.allow_premium_models

    def _eligible(self, p: Provider, min_quality: int) -> bool:
        return p.spec.quality >= min_quality and self.allowed(p.spec)

    def spent_inr(self, db: Session, since: datetime) -> Decimal:
        total = db.scalar(
            select(func.coalesce(func.sum(ModelUsage.cost_inr), 0)).where(
                ModelUsage.created_at >= since
            )
        )
        return Decimal(str(total or 0))

    def _check_budget(self, db: Session, spec: ModelSpec) -> None:
        if not spec.paid:
            return
        now = datetime.now(UTC)
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        if self.spent_inr(db, day_start) >= Decimal(str(self.settings.daily_ai_budget_inr)):
            raise BudgetExceeded("Daily AI budget reached (MATT_DAILY_AI_BUDGET_INR)")
        if self.spent_inr(db, now - timedelta(days=30)) >= Decimal(
            str(self.settings.monthly_ai_budget_inr)
        ):
            raise BudgetExceeded("Monthly AI budget reached (MATT_MONTHLY_AI_BUDGET_INR)")

    def complete(
        self,
        db: Session,
        *,
        system: str,
        prompt: str,
        task_id: int | None = None,
        min_quality: int = 1,
        max_tokens: int = 4000,
        override_budget: bool = False,
    ) -> RoutedCompletion:
        candidates = [p for p in self.providers if self._eligible(p, min_quality)]
        if not candidates:
            raise NoModelAvailable(
                "No AI model is configured. Set MATT_GEMINI_API_KEY (free) or another provider."
            )
        errors: list[str] = []
        budget_error: BudgetExceeded | None = None
        for provider in candidates:
            spec = provider.spec
            try:
                if not override_budget:
                    self._check_budget(db, spec)
            except BudgetExceeded as exc:
                budget_error = exc
                continue
            try:
                result = provider.complete(system, prompt, max_tokens)
            except ProviderError as exc:
                log.warning("model call failed", extra={"provider": spec.provider, "err": str(exc)})
                self._record(db, task_id, spec, None, str(exc))
                errors.append(str(exc))
                continue
            cost = self._record(db, task_id, spec, result, None)
            return RoutedCompletion(result, spec, cost)
        if budget_error and not errors:
            raise budget_error
        raise NoModelAvailable("All models failed: " + " | ".join(errors))

    def _record(
        self,
        db: Session,
        task_id: int | None,
        spec: ModelSpec,
        result: Completion | None,
        error: str | None,
    ) -> Decimal:
        usd = spec.cost_usd(result.prompt_tokens, result.completion_tokens) if result else 0.0
        cost = Decimal(str(round(usd * self.settings.usd_to_inr, 4)))
        db.add(
            ModelUsage(
                task_id=task_id,
                provider=spec.provider,
                model=spec.model,
                prompt_tokens=result.prompt_tokens if result else 0,
                completion_tokens=result.completion_tokens if result else 0,
                cost_inr=cost,
                latency_ms=result.latency_ms if result else 0,
                success=result is not None,
                error=error[:1000] if error else None,
            )
        )
        db.commit()
        return cost
