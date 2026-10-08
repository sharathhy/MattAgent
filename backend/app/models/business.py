"""Business data. Only legally obtainable, public business information is stored."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class Business(TimestampMixin, Base):
    __tablename__ = "businesses"
    __table_args__ = (UniqueConstraint("source", "source_ref"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(300))
    category: Mapped[str] = mapped_column(String(100), index=True)
    industry: Mapped[str | None] = mapped_column(String(100))
    location: Mapped[str | None] = mapped_column(String(500))
    city: Mapped[str | None] = mapped_column(String(100), index=True)
    country: Mapped[str | None] = mapped_column(String(100))
    website: Mapped[str | None] = mapped_column(String(500))
    public_phone: Mapped[str | None] = mapped_column(String(100))
    public_email: Mapped[str | None] = mapped_column(String(320))
    public_contact_name: Mapped[str | None] = mapped_column(String(200))
    source: Mapped[str] = mapped_column(String(50))
    source_ref: Mapped[str] = mapped_column(String(200))
    source_url: Mapped[str | None] = mapped_column(String(500))
    website_score: Mapped[int | None] = mapped_column(Integer)
    opportunity_score: Mapped[float | None] = mapped_column(Float)
    technology_stack: Mapped[list[str]] = mapped_column(JSON, default=list)
    social_links: Mapped[list[str]] = mapped_column(JSON, default=list)
    audit: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    audited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lead_status: Mapped[str | None] = mapped_column(String(20))
    outreach_status: Mapped[str | None] = mapped_column(String(20))


class Lead(TimestampMixin, Base):
    __tablename__ = "leads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id"), unique=True)
    status: Mapped[str] = mapped_column(String(20), index=True)
    service: Mapped[str] = mapped_column(String(200))
    estimated_value_min_inr: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    estimated_value_max_inr: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    outreach_draft: Mapped[str | None] = mapped_column(Text)
    next_action: Mapped[str | None] = mapped_column(String(300))
    notes: Mapped[str | None] = mapped_column(Text)

    business: Mapped[Business] = relationship()


class Opportunity(TimestampMixin, Base):
    __tablename__ = "opportunities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(300))
    category: Mapped[str] = mapped_column(String(100), index=True)
    description: Mapped[str] = mapped_column(Text)
    factors: Mapped[dict[str, float]] = mapped_column(JSON, default=dict)
    score: Mapped[float] = mapped_column(Float, index=True)
    truth: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), index=True)
    evidence: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(100))
    task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id"))


class Experiment(TimestampMixin, Base):
    __tablename__ = "experiments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(300))
    hypothesis: Mapped[str] = mapped_column(Text)
    target: Mapped[str | None] = mapped_column(String(300))
    expected: Mapped[str | None] = mapped_column(Text)
    budget_inr: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    result: Mapped[str | None] = mapped_column(Text)
    decision: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), index=True)
    #: Set when a skill bot proposed and runs this experiment itself.
    agent_slug: Mapped[str | None] = mapped_column(String(100), index=True)
    steps_done: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class Customer(TimestampMixin, Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(300))
    company: Mapped[str | None] = mapped_column(String(300))
    email: Mapped[str | None] = mapped_column(String(320))
    status: Mapped[str] = mapped_column(String(20))
    business_id: Mapped[int | None] = mapped_column(ForeignKey("businesses.id"))
    notes: Mapped[str | None] = mapped_column(Text)


class Product(TimestampMixin, Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(300))
    kind: Mapped[str] = mapped_column(String(50))
    description: Mapped[str] = mapped_column(Text)
    price_inr: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    billing: Mapped[str | None] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(20))
    url: Mapped[str | None] = mapped_column(String(500))
    spec: Mapped[str | None] = mapped_column(Text)


class LedgerEntry(TimestampMixin, Base):
    """Recorded money in or out. Facts entered by a person, never generated."""

    __tablename__ = "ledger_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(10), index=True)  # revenue | expense
    amount_inr: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    category: Mapped[str] = mapped_column(String(30), index=True)
    description: Mapped[str] = mapped_column(String(500))
    occurred_on: Mapped[date] = mapped_column(Date, index=True)
    recurring: Mapped[bool] = mapped_column(default=False)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"))
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"))
    agent_slug: Mapped[str | None] = mapped_column(String(100))
    recorded_by: Mapped[str] = mapped_column(String(100))


class Knowledge(TimestampMixin, Base):
    """Memory entries. ``expires_at`` implements retention for short-term memory."""

    __tablename__ = "knowledge"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(20), index=True)
    title: Mapped[str] = mapped_column(String(300))
    content: Mapped[str] = mapped_column(Text)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    agent_slug: Mapped[str | None] = mapped_column(String(100), index=True)
    source: Mapped[str] = mapped_column(String(100))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PaymentRequest(TimestampMixin, Base):
    """A request for a customer to pay the owner directly by UPI. MATT never holds the money;
    the request becomes revenue only when the owner confirms it arrived."""

    __tablename__ = "payment_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    reference: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    amount_inr: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    purpose: Mapped[str] = mapped_column(String(300))
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"))
    category: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(20), index=True)  # requested | received | cancelled
    upi_id: Mapped[str] = mapped_column(String(100))
    ledger_entry_id: Mapped[int | None] = mapped_column(ForeignKey("ledger_entries.id"))
    created_by: Mapped[str] = mapped_column(String(100))
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ReceivingAccount(TimestampMixin, Base):
    """Where customers pay the owner: a bank account or UPI ID. Receive-only; the account
    number or UPI ID is stored encrypted and shown masked."""

    __tablename__ = "receiving_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(10))  # bank | upi
    label: Mapped[str] = mapped_column(String(100))
    holder_name: Mapped[str] = mapped_column(String(200))
    bank_name: Mapped[str | None] = mapped_column(String(200))
    ifsc: Mapped[str | None] = mapped_column(String(11))
    secret_enc: Mapped[str] = mapped_column(Text)  # account number or UPI ID, encrypted
    last4: Mapped[str] = mapped_column(String(8))
    is_primary: Mapped[bool] = mapped_column(default=False)
    created_by: Mapped[str] = mapped_column(String(100))
