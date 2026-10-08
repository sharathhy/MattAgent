from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.llm.router import BudgetExceeded, ModelRouter, NoModelAvailable
from app.models import ModelUsage
from tests.fakes import free, paid


def test_no_provider_configured(settings: Settings, db: Session) -> None:
    router = ModelRouter(settings, providers=[])
    assert not router.available
    with pytest.raises(NoModelAvailable, match="MATT_GEMINI_API_KEY"):
        router.complete(db, system="s", prompt="p")


def test_free_first_and_fallback_recorded(settings: Settings, db: Session) -> None:
    broken, cheap = free(fail=True), paid()
    settings.free_models_only = False
    settings.daily_ai_budget_inr = settings.monthly_ai_budget_inr = 100
    router = ModelRouter(settings, providers=[cheap, broken])
    result = router.complete(db, system="s", prompt="p")
    assert result.spec.model == "fake-paid"  # free tier tried first, failed, fell through
    usage = db.scalars(select(ModelUsage).order_by(ModelUsage.id)).all()
    assert [u.success for u in usage] == [False, True]
    # 100 in * $1/M + 50 out * $2/M = $0.0002 -> INR at the configured rate
    assert usage[1].cost_inr == Decimal(str(round(0.0002 * settings.usd_to_inr, 4)))


def test_paid_models_blocked_by_zero_budget(settings: Settings, db: Session) -> None:
    settings.free_models_only = False
    router = ModelRouter(settings, providers=[paid()])
    with pytest.raises(BudgetExceeded, match="Daily"):
        router.complete(db, system="s", prompt="p")
    assert router.complete(db, system="s", prompt="p", override_budget=True).completion.text


def test_premium_needs_opt_in(settings: Settings, db: Session) -> None:
    premium = paid()
    object.__setattr__(premium.spec, "tier", "premium")
    settings.free_models_only = False
    assert not ModelRouter(settings, providers=[premium]).available
    settings.allow_premium_models = True
    assert ModelRouter(settings, providers=[premium]).available
