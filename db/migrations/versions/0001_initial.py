"""Initial migration: users + orders tables.

Revision ID: 0001
Revises:
Create Date: 2026-04-27

NOTE: This migration uses synchronous psycopg2 (via Alembic env.py).
      Standard `op.execute("CREATE TYPE ...")` and `PGENUM(create_type=False)`
      work correctly — no asyncpg enum auto-create bug here.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ENUM as PGENUM
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None

# Reusable ENUM types with create_type=False — enums are created via op.execute below
order_status = PGENUM(
    "pending",
    "escrow_held",
    "completed",
    "dispute",
    "cancelled",
    name="order_status",
    create_type=False,
)
supported_asset = PGENUM(
    "BTC",
    "TON",
    "USDT",
    "USDC",
    "ETH",
    name="supported_asset",
    create_type=False,
)


def upgrade() -> None:
    # ── Create PostgreSQL ENUM types ────────────────────────────────────────────
    # Plain op.execute works reliably with psycopg2 (sync Alembic engine).
    op.execute(
        "CREATE TYPE order_status AS ENUM "
        "('pending', 'escrow_held', 'completed', 'dispute', 'cancelled')"
    )
    op.execute("CREATE TYPE supported_asset AS ENUM ('BTC', 'TON', 'USDT', 'USDC', 'ETH')")

    # ── users ───────────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(64), nullable=True),
        sa.Column("first_name", sa.String(128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_banned", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "daily_volume_usdt",
            sa.Numeric(precision=18, scale=2),
            nullable=False,
            server_default="0",
        ),
        sa.Column("daily_volume_reset_at", sa.DateTime(timezone=True), nullable=True),
        # Encrypted exchange API keys (AES-256-GCM, stored as hex)
        sa.Column("binance_api_key_enc", sa.String(512), nullable=True),
        sa.Column("binance_api_secret_enc", sa.String(512), nullable=True),
        sa.Column("okx_api_key_enc", sa.String(512), nullable=True),
        sa.Column("okx_api_secret_enc", sa.String(512), nullable=True),
        sa.Column("bybit_api_key_enc", sa.String(512), nullable=True),
        sa.Column("bybit_api_secret_enc", sa.String(512), nullable=True),
        sa.PrimaryKeyConstraint("telegram_id"),
    )

    # ── orders ──────────────────────────────────────────────────────────────────
    op.create_table(
        "orders",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("buyer_id", sa.BigInteger(), nullable=False),
        sa.Column("seller_id", sa.BigInteger(), nullable=True),
        # ENUM columns: create_type=False because types created above via op.execute
        sa.Column("asset", supported_asset, nullable=False),
        sa.Column("amount", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column("fiat_amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("fiat_currency", sa.String(10), nullable=False),
        sa.Column(
            "status",
            order_status,
            nullable=False,
            server_default="pending",
        ),
        sa.Column("fiat_confirmed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("invoice_id", sa.String(128), nullable=True),
        sa.Column("spend_id", sa.String(128), nullable=True),
        sa.Column("crypto_pay_payload", sa.Text(), nullable=True),
        sa.Column("payment_url", sa.Text(), nullable=True),
        sa.Column("fee_percent", sa.Numeric(6, 4), nullable=False, server_default="0"),
        sa.Column("fee_fixed", sa.Numeric(18, 8), nullable=False, server_default="0"),
        sa.Column("total_fee", sa.Numeric(18, 8), nullable=False, server_default="0"),
        sa.Column("dispute_reason", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["buyer_id"], ["users.telegram_id"]),
        sa.ForeignKeyConstraint(["seller_id"], ["users.telegram_id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("invoice_id"),
        sa.UniqueConstraint("spend_id"),
    )

    op.create_index("ix_orders_buyer_id", "orders", ["buyer_id"])
    op.create_index("ix_orders_seller_id", "orders", ["seller_id"])
    op.create_index("ix_orders_status", "orders", ["status"])


def downgrade() -> None:
    op.drop_index("ix_orders_status", table_name="orders")
    op.drop_index("ix_orders_seller_id", table_name="orders")
    op.drop_index("ix_orders_buyer_id", table_name="orders")
    op.drop_table("orders")
    op.drop_table("users")
    op.execute("DROP TYPE IF EXISTS order_status")
    op.execute("DROP TYPE IF EXISTS supported_asset")
