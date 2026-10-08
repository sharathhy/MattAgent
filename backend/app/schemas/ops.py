from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CommandRequest(BaseModel):
    text: str = Field(max_length=4000)


class CommandResponse(BaseModel):
    reply: str
    intent: str
    task_id: int | None
    data: dict[str, Any]


class TaskCreate(BaseModel):
    objective: str = Field(min_length=3, max_length=4000)
    agent_slug: str = "ceo"
    priority: int = Field(default=5, ge=1, le=10)
    context: dict[str, Any] | None = None


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    objective: str
    agent_slug: str | None = None
    parent_id: int | None
    status: str
    priority: int
    input: dict[str, Any]
    output: str | None
    output_data: dict[str, Any] | None
    error: str | None
    attempts: int
    max_attempts: int
    next_attempt_at: datetime | None
    model: str | None
    cost_inr: Decimal
    tokens: int
    created_by: str
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class WorkflowInfo(BaseModel):
    slug: str
    description: str
    needs_ai_model: bool
    ready: bool


class WorkflowRunRequest(BaseModel):
    params: dict[str, Any] = Field(default_factory=dict)


class ToolOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    slug: str
    name: str
    description: str
    provider: str
    cost_tier: str
    permission: str
    risk_level: str
    input_schema: dict[str, Any]
    available: bool
    version: str


class ApprovalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: int | None
    agent_slug: str
    action: str
    kind: str
    details: dict[str, Any]
    estimated_cost_inr: Decimal
    risk_level: str
    status: str
    decided_by: str | None
    decided_at: datetime | None
    note: str | None
    created_at: datetime


class ApprovalDecision(BaseModel):
    approve: bool
    note: str | None = Field(default=None, max_length=2000)


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: str
    payload: dict[str, Any]
    created_at: datetime


class AutopilotUpdate(BaseModel):
    enabled: bool | None = None
    cities: list[str] | None = Field(default=None, min_length=1, max_length=20)
    categories: list[str] | None = Field(default=None, min_length=1, max_length=16)
    interval_minutes: int | None = Field(default=None, ge=10, le=1440)
    daily_outreach_drafts: int | None = Field(default=None, ge=0, le=50)
