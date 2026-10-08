from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, utcnow


class Agent(TimestampMixin, Base):
    """A worker in the AI workforce: the CEO, an executive, a skill, or a meta-skill.

    Performance fields stay NULL until real task results exist; nothing is estimated here.
    """

    __tablename__ = "agents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(20), index=True)
    department: Mapped[str] = mapped_column(String(50), index=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("agents.id"), index=True)
    description: Mapped[str] = mapped_column(Text)

    capabilities: Mapped[list[str]] = mapped_column(JSON, default=list)
    inputs: Mapped[list[str]] = mapped_column(JSON, default=list)
    outputs: Mapped[list[str]] = mapped_column(JSON, default=list)
    tools: Mapped[list[str]] = mapped_column(JSON, default=list)
    permissions: Mapped[list[str]] = mapped_column(JSON, default=list)
    dependencies: Mapped[list[str]] = mapped_column(JSON, default=list)

    cost_tier: Mapped[str] = mapped_column(String(20))
    level: Mapped[str] = mapped_column(String(30), default="standard")
    version: Mapped[str] = mapped_column(String(20), default="1.0.0")
    status: Mapped[str] = mapped_column(String(20), index=True)

    performance_score: Mapped[float | None] = mapped_column(Float)
    success_rate: Mapped[float | None] = mapped_column(Float)
    revenue_contribution: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    tasks_completed: Mapped[int] = mapped_column(Integer, default=0)
    tasks_failed: Mapped[int] = mapped_column(Integer, default=0)
    last_upgraded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    parent: Mapped["Agent | None"] = relationship(remote_side=[id], back_populates="reports")
    reports: Mapped[list["Agent"]] = relationship(back_populates="parent")
    versions: Mapped[list["AgentVersion"]] = relationship(
        back_populates="agent", order_by="AgentVersion.id", cascade="all, delete-orphan"
    )


class AgentVersion(Base):
    """Immutable record of each agent definition change."""

    __tablename__ = "agent_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"), index=True)
    version: Mapped[str] = mapped_column(String(20))
    change_summary: Mapped[str] = mapped_column(Text)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_by: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    agent: Mapped[Agent] = relationship(back_populates="versions")
