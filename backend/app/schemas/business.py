from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.domain import LeadStatus, RevenueCategory


class _Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


class BusinessOut(_Out):
    name: str
    category: str
    city: str | None
    country: str | None
    location: str | None
    website: str | None
    public_phone: str | None
    public_email: str | None
    source: str
    source_url: str | None
    website_score: int | None
    opportunity_score: float | None
    technology_stack: list[str]
    social_links: list[str]
    audit: dict[str, Any] | None
    audited_at: datetime | None
    lead_status: str | None
    outreach_status: str | None


class LeadOut(_Out):
    business_id: int
    status: str
    service: str
    estimated_value_min_inr: Decimal | None
    estimated_value_max_inr: Decimal | None
    outreach_draft: str | None
    next_action: str | None
    notes: str | None
    business: BusinessOut


class LeadUpdate(BaseModel):
    status: LeadStatus | None = None
    next_action: str | None = Field(default=None, max_length=300)
    notes: str | None = Field(default=None, max_length=5000)


class OpportunityIn(BaseModel):
    title: str = Field(min_length=3, max_length=300)
    category: str = Field(default="other", max_length=100)
    description: str = Field(default="", max_length=5000)
    factors: dict[str, float] = Field(default_factory=dict)
    evidence: str | None = Field(default=None, max_length=5000)


class OpportunityUpdate(BaseModel):
    status: Literal["proposed", "validating", "approved", "rejected", "launched"] | None = None
    factors: dict[str, float] | None = None


class OpportunityOut(_Out):
    title: str
    category: str
    description: str
    factors: dict[str, float]
    score: float
    truth: str
    status: str
    evidence: str | None
    source: str
    task_id: int | None


class CustomerIn(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    company: str | None = Field(default=None, max_length=300)
    email: str | None = Field(default=None, max_length=320)
    status: Literal["prospect", "active", "churned"] = "active"
    business_id: int | None = None
    notes: str | None = Field(default=None, max_length=5000)


class CustomerOut(_Out):
    name: str
    company: str | None
    email: str | None
    status: str
    business_id: int | None
    notes: str | None


class ProductIn(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    kind: Literal["service", "saas", "digital_product", "subscription", "other"] = "service"
    description: str = Field(default="", max_length=5000)
    price_inr: Decimal | None = Field(default=None, ge=0)
    billing: Literal["one_time", "monthly", "yearly"] | None = None
    status: Literal["idea", "building", "live", "retired"] = "idea"
    url: str | None = Field(default=None, max_length=500)
    spec: str | None = Field(default=None, max_length=20000)


class ProductOut(_Out):
    name: str
    kind: str
    description: str
    price_inr: Decimal | None
    billing: str | None
    status: str
    url: str | None
    spec: str | None


class LedgerIn(BaseModel):
    kind: Literal["revenue", "expense"]
    amount_inr: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    category: RevenueCategory = RevenueCategory.OTHER
    description: str = Field(min_length=1, max_length=500)
    occurred_on: date
    recurring: bool = False
    customer_id: int | None = None
    product_id: int | None = None
    agent_slug: str | None = None


class LedgerOut(_Out):
    kind: str
    amount_inr: Decimal
    category: str
    description: str
    occurred_on: date
    recurring: bool
    customer_id: int | None
    product_id: int | None
    agent_slug: str | None
    recorded_by: str


class ExperimentIn(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    hypothesis: str = Field(min_length=1, max_length=5000)
    target: str | None = Field(default=None, max_length=300)
    expected: str | None = Field(default=None, max_length=5000)
    budget_inr: Decimal = Field(default=Decimal("0"), ge=0)
    result: str | None = Field(default=None, max_length=5000)
    decision: str | None = Field(default=None, max_length=5000)
    status: Literal["planned", "running", "completed", "stopped"] = "planned"


class ExperimentOut(_Out):
    name: str
    hypothesis: str
    target: str | None
    expected: str | None
    budget_inr: Decimal
    result: str | None
    decision: str | None
    status: str


class KnowledgeIn(BaseModel):
    kind: Literal["short_term", "long_term", "business", "customer", "agent", "procedure"] = (
        "long_term"
    )
    title: str = Field(min_length=1, max_length=300)
    content: str = Field(min_length=1, max_length=50000)
    tags: list[str] = Field(default_factory=list, max_length=20)
    agent_slug: str | None = None
    retention_days: int | None = Field(default=None, ge=1, le=3650)


class KnowledgeOut(_Out):
    kind: str
    title: str
    content: str
    tags: list[str]
    agent_slug: str | None
    source: str
    expires_at: datetime | None
