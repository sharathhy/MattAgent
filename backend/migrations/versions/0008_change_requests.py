"""owner change requests for MATT's own code

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-08 19:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "change_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("request", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("plan", sa.Text(), nullable=True),
        sa.Column("files", sa.JSON(), nullable=False),
        sa.Column("diff", sa.Text(), nullable=True),
        sa.Column("base_sha", sa.String(length=64), nullable=True),
        sa.Column("branch", sa.String(length=200), nullable=True),
        sa.Column("pr_url", sa.String(length=500), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("model", sa.String(length=100), nullable=True),
        sa.Column("approval_id", sa.Integer(), nullable=True),
        sa.Column("task_id", sa.Integer(), nullable=True),
        sa.Column("created_by", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["approval_id"], ["approvals.id"],
            name=op.f("fk_change_requests_approval_id_approvals"),
        ),
        sa.ForeignKeyConstraint(
            ["task_id"], ["tasks.id"], name=op.f("fk_change_requests_task_id_tasks")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_change_requests")),
    )  # fmt: skip
    op.create_index(op.f("ix_change_requests_status"), "change_requests", ["status"])


def downgrade() -> None:
    op.drop_index(op.f("ix_change_requests_status"), table_name="change_requests")
    op.drop_table("change_requests")
