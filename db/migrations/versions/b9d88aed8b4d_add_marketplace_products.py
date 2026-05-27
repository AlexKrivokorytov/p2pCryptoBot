"""add_marketplace_products

Revision ID: b9d88aed8b4d
Revises: d1e8ea476e1b
Create Date: 2026-05-14 10:39:15.834250
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b9d88aed8b4d"
down_revision: str | None = "d1e8ea476e1b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
            "products",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("seller_id", sa.BigInteger(), nullable=False),
            sa.Column("title", sa.String(length=128), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("is_digital", sa.Boolean(), nullable=False),
            sa.Column("digital_content", sa.Text(), nullable=True),
            sa.Column("price", sa.Numeric(precision=18, scale=2), nullable=False),
            sa.Column(
                "currency_type",
                sa.Enum("XTR", "FIAT", "CRYPTO", name="product_currency_type"),
                nullable=False,
            ),
            sa.Column("fiat_currency", sa.String(length=10), nullable=True),
            sa.Column("crypto_asset", sa.String(length=10), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(["seller_id"], ["users.telegram_id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
    op.create_index(op.f("ix_products_seller_id"), "products", ["seller_id"], unique=False)
    op.create_table(
            "marketplace_deals",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("product_id", sa.UUID(), nullable=False),
            sa.Column("buyer_id", sa.BigInteger(), nullable=False),
            sa.Column(
                "status",
                sa.Enum(
                    "created",
                    "paid",
                    "delivered",
                    "completed",
                    "dispute",
                    "cancelled",
                    name="deal_status",
                ),
                nullable=False,
            ),
            sa.Column("amount", sa.Numeric(precision=18, scale=2), nullable=False),
            sa.Column(
                "currency_type",
                sa.Enum("XTR", "FIAT", "CRYPTO", name="deal_currency_type"),
                nullable=False,
            ),
            sa.Column("provider_payment_charge_id", sa.String(length=255), nullable=True),
            sa.Column("telegram_payment_charge_id", sa.String(length=255), nullable=True),
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
            sa.ForeignKeyConstraint(["buyer_id"], ["users.telegram_id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
            sa.PrimaryKeyConstraint("id"),
        )
    op.create_index(
            op.f("ix_marketplace_deals_buyer_id"), "marketplace_deals", ["buyer_id"], unique=False
        )
    op.create_index(
            op.f("ix_marketplace_deals_product_id"), "marketplace_deals", ["product_id"], unique=False
        )
    op.create_index(
            op.f("ix_marketplace_deals_status"), "marketplace_deals", ["status"], unique=False
        )


def downgrade() -> None:
    op.drop_index(op.f("ix_products_seller_id"), table_name="products")
    op.drop_table("products")
    op.drop_index(op.f("ix_marketplace_deals_status"), table_name="marketplace_deals")
    op.drop_index(op.f("ix_marketplace_deals_product_id"), table_name="marketplace_deals")
    op.drop_index(op.f("ix_marketplace_deals_buyer_id"), table_name="marketplace_deals")
    op.drop_table("marketplace_deals")
