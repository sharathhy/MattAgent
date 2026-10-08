"""free model scout sources

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-08 17:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "model_sources",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("model", sa.String(length=200), nullable=True),
        sa.Column("free_models", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_model_sources")),
    )
    op.create_index(op.f("ix_model_sources_slug"), "model_sources", ["slug"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_model_sources_slug"), table_name="model_sources")
    op.drop_table("model_sources")
