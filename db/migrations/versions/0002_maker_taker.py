"""maker_taker

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-28

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM as PGENUM


revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Create order_type ENUM
    op.execute("CREATE TYPE order_type AS ENUM ('sell_crypto', 'buy_crypto')")

    # 2. Add new values to order_status ENUM
    # Postgres doesn't easily support dropping/renaming values. We add the new ones.
    # Note: ADD VALUE cannot be executed inside a transaction block in older postgres,
    # but Alembic usually commits before DDL or runs outside transaction.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE order_status ADD VALUE IF NOT EXISTS 'pending_funding' BEFORE 'escrow_held'")
        op.execute("ALTER TYPE order_status ADD VALUE IF NOT EXISTS 'active' BEFORE 'escrow_held'")

    # 3. Rename columns buyer_id -> maker_id, seller_id -> taker_id
    op.alter_column('orders', 'buyer_id', new_column_name='maker_id')
    op.alter_column('orders', 'seller_id', new_column_name='taker_id')

    # Rename the indices manually
    op.execute("ALTER INDEX ix_orders_buyer_id RENAME TO ix_orders_maker_id")
    op.execute("ALTER INDEX ix_orders_seller_id RENAME TO ix_orders_taker_id")

    # 4. Add new columns: order_type, payment_method
    op.add_column('orders', sa.Column('order_type', sa.Enum('sell_crypto', 'buy_crypto', name='order_type', create_type=False), nullable=True))
    op.add_column('orders', sa.Column('payment_method', sa.String(length=64), nullable=True))

    # Populate existing rows so we can make columns non-nullable
    op.execute("UPDATE orders SET order_type = 'sell_crypto'")
    op.execute("UPDATE orders SET payment_method = 'Unknown'")
    op.execute("UPDATE orders SET status = 'pending_funding' WHERE status = 'pending'")

    # Make them non-nullable
    op.alter_column('orders', 'order_type', nullable=False)
    op.alter_column('orders', 'payment_method', nullable=False)


def downgrade() -> None:
    # 1. Drop new columns
    op.drop_column('orders', 'payment_method')
    op.drop_column('orders', 'order_type')

    # 2. Rename columns back
    op.alter_column('orders', 'taker_id', new_column_name='seller_id')
    op.alter_column('orders', 'maker_id', new_column_name='buyer_id')

    op.execute("ALTER INDEX ix_orders_taker_id RENAME TO ix_orders_seller_id")
    op.execute("ALTER INDEX ix_orders_maker_id RENAME TO ix_orders_buyer_id")

    op.execute("UPDATE orders SET status = 'pending' WHERE status IN ('pending_funding', 'active')")

    # Note: We do not drop the enum values for order_status because Postgres doesn't support it natively.
    op.execute("DROP TYPE IF EXISTS order_type")
