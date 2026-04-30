"""user_stats

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-28

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users", sa.Column("total_trades", sa.BigInteger(), server_default="0", nullable=False)
    )
    op.add_column(
        "users", sa.Column("successful_trades", sa.BigInteger(), server_default="0", nullable=False)
    )


def downgrade() -> None:
    op.drop_column("users", "successful_trades")
    op.drop_column("users", "total_trades")
