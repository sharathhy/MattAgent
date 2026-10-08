"""receive-only UPI payment requests

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-08 17:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "payment_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("reference", sa.String(length=40), nullable=False),
        sa.Column("amount_inr", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("purpose", sa.String(length=300), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=True),
        sa.Column("category", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("upi_id", sa.String(length=100), nullable=False),
        sa.Column("ledger_entry_id", sa.Integer(), nullable=True),
        sa.Column("created_by", sa.String(length=100), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["customer_id"], ["customers.id"],
            name=op.f("fk_payment_requests_customer_id_customers"),
        ),
        sa.ForeignKeyConstraint(
            ["ledger_entry_id"], ["ledger_entries.id"],
            name=op.f("fk_payment_requests_ledger_entry_id_ledger_entries"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payment_requests")),
    )  # fmt: skip
    op.create_index(
        op.f("ix_payment_requests_reference"), "payment_requests", ["reference"], unique=True
    )
    op.create_index(op.f("ix_payment_requests_status"), "payment_requests", ["status"])


def downgrade() -> None:
    op.drop_index(op.f("ix_payment_requests_status"), table_name="payment_requests")
    op.drop_index(op.f("ix_payment_requests_reference"), table_name="payment_requests")
    op.drop_table("payment_requests")
