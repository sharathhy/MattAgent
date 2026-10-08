"""trading desk and bot swarm

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-08 13:28:06.564481
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "broker_accounts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("broker", sa.String(length=20), nullable=False),
        sa.Column("label", sa.String(length=100), nullable=False),
        sa.Column("client_id", sa.String(length=50), nullable=False),
        sa.Column("api_key_enc", sa.Text(), nullable=False),
        sa.Column("api_secret_enc", sa.Text(), nullable=False),
        sa.Column("access_token_enc", sa.Text(), nullable=True),
        sa.Column("token_day", sa.String(length=10), nullable=True),
        sa.Column("funds_inr", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_broker_accounts")),
    )
    op.create_table(
        "market_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=50), nullable=False),
        sa.Column("symbol", sa.String(length=30), nullable=False),
        sa.Column("market", sa.String(length=10), nullable=False),
        sa.Column("interval", sa.String(length=10), nullable=False),
        sa.Column("price_inr", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("change_pct", sa.Float(), nullable=False),
        sa.Column("candles", sa.JSON(), nullable=False),
        sa.Column("indicators", sa.JSON(), nullable=False),
        sa.Column("patterns", sa.JSON(), nullable=False),
        sa.Column("last_candle_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_market_snapshots")),
    )
    with op.batch_alter_table("market_snapshots", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_market_snapshots_key"), ["key"], unique=True)
        batch_op.create_index(batch_op.f("ix_market_snapshots_symbol"), ["symbol"], unique=False)

    op.create_table(
        "trading_account",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("mode", sa.String(length=10), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("kill_switch", sa.Boolean(), nullable=False),
        sa.Column("starting_capital", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("cash", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("realized_pnl", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("fees_paid", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("peak_equity", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("day", sa.String(length=10), nullable=True),
        sa.Column("day_start_equity", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("goal_inr", sa.Numeric(precision=20, scale=2), nullable=False),
        sa.Column("max_trade_risk_pct", sa.Float(), nullable=False),
        sa.Column("max_day_loss_pct", sa.Float(), nullable=False),
        sa.Column("max_open_positions", sa.Integer(), nullable=False),
        sa.Column("live_capital_cap_inr", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("live_confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("live_confirmed_by", sa.String(length=100), nullable=True),
        sa.Column("halted_reason", sa.String(length=300), nullable=True),
        sa.Column("halted_day", sa.String(length=10), nullable=True),
        sa.Column("bot_cursor", sa.Integer(), nullable=False),
        sa.Column("last_tick_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("equity_curve", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_trading_account")),
    )
    op.create_table(
        "trading_bots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("symbol", sa.String(length=30), nullable=True),
        sa.Column("interval", sa.String(length=10), nullable=True),
        sa.Column("strategy", sa.String(length=50), nullable=True),
        sa.Column("topic", sa.String(length=300), nullable=True),
        sa.Column("params", sa.JSON(), nullable=False),
        sa.Column("memory", sa.JSON(), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("runs", sa.Integer(), nullable=False),
        sa.Column("trades", sa.Integer(), nullable=False),
        sa.Column("wins", sa.Integer(), nullable=False),
        sa.Column("losses", sa.Integer(), nullable=False),
        sa.Column("pnl", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("fitness", sa.Float(), nullable=False),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_trading_bots")),
    )
    with op.batch_alter_table("trading_bots", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_trading_bots_role"), ["role"], unique=False)
        batch_op.create_index(batch_op.f("ix_trading_bots_slug"), ["slug"], unique=True)
        batch_op.create_index(batch_op.f("ix_trading_bots_symbol"), ["symbol"], unique=False)

    op.create_table(
        "trading_insights",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("symbol", sa.String(length=30), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("url", sa.String(length=1000), nullable=True),
        sa.Column("sentiment", sa.Float(), nullable=True),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("bot_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["bot_id"], ["trading_bots.id"], name=op.f("fk_trading_insights_bot_id_trading_bots")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_trading_insights")),
    )
    with op.batch_alter_table("trading_insights", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_trading_insights_created_at"), ["created_at"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_trading_insights_kind"), ["kind"], unique=False)
        batch_op.create_index(batch_op.f("ix_trading_insights_symbol"), ["symbol"], unique=False)

    op.create_table(
        "trading_trades",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("mode", sa.String(length=10), nullable=False),
        sa.Column("symbol", sa.String(length=30), nullable=False),
        sa.Column("market", sa.String(length=10), nullable=False),
        sa.Column("side", sa.String(length=5), nullable=False),
        sa.Column("qty", sa.Numeric(precision=24, scale=8), nullable=False),
        sa.Column("entry_price", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("stop_price", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("target_price", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("exit_price", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("last_price", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("exit_reason", sa.String(length=50), nullable=True),
        sa.Column("pnl", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("fees", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("trader_bot_id", sa.Integer(), nullable=True),
        sa.Column("strategist_bot_id", sa.Integer(), nullable=True),
        sa.Column("strategy", sa.String(length=50), nullable=True),
        sa.Column("features", sa.JSON(), nullable=False),
        sa.Column("broker_orders", sa.JSON(), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["strategist_bot_id"],
            ["trading_bots.id"],
            name=op.f("fk_trading_trades_strategist_bot_id_trading_bots"),
        ),
        sa.ForeignKeyConstraint(
            ["trader_bot_id"],
            ["trading_bots.id"],
            name=op.f("fk_trading_trades_trader_bot_id_trading_bots"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_trading_trades")),
    )
    with op.batch_alter_table("trading_trades", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_trading_trades_mode"), ["mode"], unique=False)
        batch_op.create_index(batch_op.f("ix_trading_trades_status"), ["status"], unique=False)
        batch_op.create_index(batch_op.f("ix_trading_trades_symbol"), ["symbol"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_trading_trades_trader_bot_id"), ["trader_bot_id"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("trading_trades", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_trading_trades_trader_bot_id"))
        batch_op.drop_index(batch_op.f("ix_trading_trades_symbol"))
        batch_op.drop_index(batch_op.f("ix_trading_trades_status"))
        batch_op.drop_index(batch_op.f("ix_trading_trades_mode"))

    op.drop_table("trading_trades")
    with op.batch_alter_table("trading_insights", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_trading_insights_symbol"))
        batch_op.drop_index(batch_op.f("ix_trading_insights_kind"))
        batch_op.drop_index(batch_op.f("ix_trading_insights_created_at"))

    op.drop_table("trading_insights")
    with op.batch_alter_table("trading_bots", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_trading_bots_symbol"))
        batch_op.drop_index(batch_op.f("ix_trading_bots_slug"))
        batch_op.drop_index(batch_op.f("ix_trading_bots_role"))

    op.drop_table("trading_bots")
    op.drop_table("trading_account")
    with op.batch_alter_table("market_snapshots", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_market_snapshots_symbol"))
        batch_op.drop_index(batch_op.f("ix_market_snapshots_key"))

    op.drop_table("market_snapshots")
    op.drop_table("broker_accounts")
