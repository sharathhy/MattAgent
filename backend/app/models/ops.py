"""Orchestration tables: tools, tasks, workflow runs, approvals, events, model usage."""

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, utcnow
from app.models.agent import Agent


class Tool(TimestampMixin, Base):
    __tablename__ = "tools"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    provider: Mapped[str] = mapped_column(String(100))
    cost_tier: Mapped[str] = mapped_column(String(20))
    permission: Mapped[str] = mapped_column(String(30))
    risk_level: Mapped[str] = mapped_column(String(10))
    input_schema: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    output_schema: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    available: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[str] = mapped_column(String(20), default="1.0.0")


class WorkflowRun(TimestampMixin, Base):
    __tablename__ = "workflow_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workflow: Mapped[str] = mapped_column(String(100), index=True)
    status: Mapped[str] = mapped_column(String(20), index=True)
    params: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(100))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Task(TimestampMixin, Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(20), default="agent")  # agent | command | workflow
    objective: Mapped[str] = mapped_column(Text)
    agent_id: Mapped[int | None] = mapped_column(ForeignKey("agents.id"), index=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id"), index=True)
    workflow_run_id: Mapped[int | None] = mapped_column(ForeignKey("workflow_runs.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), index=True)
    priority: Mapped[int] = mapped_column(Integer, default=5)
    input: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    output: Mapped[str | None] = mapped_column(Text)
    output_data: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    model: Mapped[str | None] = mapped_column(String(100))
    cost_inr: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=Decimal("0"))
    tokens: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[str] = mapped_column(String(100))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    agent: Mapped[Agent | None] = relationship()


class Approval(TimestampMixin, Base):
    __tablename__ = "approvals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id"), index=True)
    agent_slug: Mapped[str] = mapped_column(String(100))
    action: Mapped[str] = mapped_column(String(300))
    kind: Mapped[str] = mapped_column(String(50))  # e.g. outreach, budget, permission
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    estimated_cost_inr: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    risk_level: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(20), index=True)
    decided_by: Mapped[str | None] = mapped_column(String(100))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    note: Mapped[str | None] = mapped_column(Text)


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[str] = mapped_column(String(50), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )


class ModelUsage(Base):
    __tablename__ = "model_usage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id"), index=True)
    provider: Mapped[str] = mapped_column(String(50))
    model: Mapped[str] = mapped_column(String(100))
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_inr: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=Decimal("0"))
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    success: Mapped[bool] = mapped_column(Boolean)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )


class Autopilot(TimestampMixin, Base):
    """Single-row configuration for MATT's self-directed work loop."""

    __tablename__ = "autopilot"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    cities: Mapped[list[str]] = mapped_column(JSON, default=list)
    categories: Mapped[list[str]] = mapped_column(JSON, default=list)
    interval_minutes: Mapped[int] = mapped_column(Integer, default=15)
    daily_outreach_drafts: Mapped[int] = mapped_column(Integer, default=5)
    cursor: Mapped[int] = mapped_column(Integer, default=0)
    last_cycle_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_cycle_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_action: Mapped[str | None] = mapped_column(String(300))
    updated_by: Mapped[str | None] = mapped_column(String(100))
    #: Heartbeat: when the background scheduler last checked in (proves it runs on its own).
    last_tick_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: Skill bots: how many independent skill turns a day (kept well inside free AI limits).
    daily_bot_tasks: Mapped[int] = mapped_column(Integer, default=48, server_default="48")
    bot_cursor: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class ModelSource(TimestampMixin, Base):
    """What the Free Model Scout last found for one free-tier AI service."""

    __tablename__ = "model_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(20))  # ok, not_connected, error, no_free_model
    model: Mapped[str | None] = mapped_column(String(200))
    free_models: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ChangeRequest(TimestampMixin, Base):
    """A change to MATT's own code that the owner asked for. MATT drafts it; the owner approves
    it; MATT opens a pull request; the owner merges it. MATT never merges or deploys itself."""

    __tablename__ = "change_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), index=True)
    plan: Mapped[str | None] = mapped_column(Text)
    files: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    diff: Mapped[str | None] = mapped_column(Text)
    base_sha: Mapped[str | None] = mapped_column(String(64))
    branch: Mapped[str | None] = mapped_column(String(200))
    pr_url: Mapped[str | None] = mapped_column(String(500))
    error: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(String(100))
    approval_id: Mapped[int | None] = mapped_column(ForeignKey("approvals.id"))
    task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id"))
    created_by: Mapped[str] = mapped_column(String(100))
