from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, computed_field

from app.core.domain import HIGH_RISK_PERMISSIONS, AgentKind, AgentStatus, CostTier, Permission


class AgentSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    slug: str
    name: str
    role: str
    kind: AgentKind
    department: str
    status: AgentStatus
    level: str
    version: str
    cost_tier: CostTier
    permissions: list[Permission]
    performance_score: float | None
    success_rate: float | None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def requires_approval(self) -> bool:
        return bool(set(self.permissions) & HIGH_RISK_PERMISSIONS)


class AgentVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    version: str
    change_summary: str
    created_by: str
    created_at: datetime
    snapshot: dict[str, Any]


class AgentDetail(AgentSummary):
    description: str
    capabilities: list[str]
    inputs: list[str]
    outputs: list[str]
    tools: list[str]
    dependencies: list[str]
    parent_slug: str | None
    report_slugs: list[str]
    revenue_contribution: Decimal
    tasks_completed: int
    tasks_failed: int
    created_at: datetime
    updated_at: datetime
    last_upgraded_at: datetime | None
    versions: list[AgentVersionOut]


class HierarchyNode(BaseModel):
    slug: str
    name: str
    role: str
    kind: AgentKind
    department: str
    status: AgentStatus
    children: list["HierarchyNode"] = []


class RegistrySummary(BaseModel):
    total: int
    by_kind: dict[str, int]
    by_department: dict[str, int]
    by_status: dict[str, int]


class StatusChangeRequest(BaseModel):
    status: AgentStatus
    reason: str = Field(default="", max_length=500)


class PermissionChangeRequest(BaseModel):
    permissions: list[Permission]
    reason: str = Field(min_length=3, max_length=500)
