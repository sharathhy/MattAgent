from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.core.domain import CostTier, Permission, RiskLevel


@dataclass(frozen=True)
class ToolDefinition:
    slug: str
    name: str
    description: str
    provider: str
    cost_tier: CostTier
    permission: Permission
    risk_level: RiskLevel
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    run: Callable[..., dict[str, Any]] | None = field(default=None, compare=False)
    version: str = "1.0.0"
