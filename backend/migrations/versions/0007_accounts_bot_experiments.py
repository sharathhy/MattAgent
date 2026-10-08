"""receiving accounts and skill-bot experiments

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-08 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "receiving_accounts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("label", sa.String(length=100), nullable=False),
        sa.Column("holder_name", sa.String(length=200), nullable=False),
        sa.Column("bank_name", sa.String(length=200), nullable=True),
        sa.Column("ifsc", sa.String(length=11), nullable=True),
        sa.Column("secret_enc", sa.Text(), nullable=False),
        sa.Column("last4", sa.String(length=8), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_receiving_accounts")),
    )
    with op.batch_alter_table("experiments") as batch:
        batch.add_column(sa.Column("agent_slug", sa.String(length=100), nullable=True))
        batch.add_column(
            sa.Column("steps_done", sa.Integer(), nullable=False, server_default="0")
        )
        batch.create_index(batch.f("ix_experiments_agent_slug"), ["agent_slug"])


def downgrade() -> None:
    with op.batch_alter_table("experiments") as batch:
        batch.drop_index(batch.f("ix_experiments_agent_slug"))
        batch.drop_column("steps_done")
        batch.drop_column("agent_slug")
    op.drop_table("receiving_accounts")
