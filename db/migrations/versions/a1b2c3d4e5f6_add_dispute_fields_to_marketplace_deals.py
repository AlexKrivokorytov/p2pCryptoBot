"""Add dispute tracking fields to marketplace_deals.

Revision ID: a1b2c3d4e5f6
Revises: caade745ecb9
Create Date: 2026-05-21 11:00:00.000000

Phase 10: Embeds dispute tracking directly into marketplace_deals rows.
Each deal can have at most one dispute, so inline columns are more efficient
than a JOIN to a separate table.

Fields added:
- dispute_reason: text description of the dispute.
- dispute_opened_at: timestamp when the dispute was opened.
- dispute_resolved_by: admin telegram_id who resolved the dispute.
- dispute_resolution: "buyer" or "seller" — who won the dispute.
- dispute_resolution_comment: optional admin comment.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "caade745ecb9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add dispute tracking columns to marketplace_deals."""
    op.add_column(
        "marketplace_deals",
        sa.Column("dispute_reason", sa.Text(), nullable=True),
    )
    op.add_column(
        "marketplace_deals",
        sa.Column("dispute_opened_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "marketplace_deals",
        sa.Column("dispute_resolved_by", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "marketplace_deals",
        sa.Column("dispute_resolution", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "marketplace_deals",
        sa.Column("dispute_resolution_comment", sa.Text(), nullable=True),
    )
    # Index for fast filtering of all open disputes in admin queue
    op.create_index(
        "ix_marketplace_deals_dispute_opened_at",
        "marketplace_deals",
        ["dispute_opened_at"],
        unique=False,
    )


def downgrade() -> None:
    """Remove dispute tracking columns from marketplace_deals."""
    op.drop_index(
        "ix_marketplace_deals_dispute_opened_at",
        table_name="marketplace_deals",
    )
    op.drop_column("marketplace_deals", "dispute_resolution_comment")
    op.drop_column("marketplace_deals", "dispute_resolution")
    op.drop_column("marketplace_deals", "dispute_resolved_by")
    op.drop_column("marketplace_deals", "dispute_opened_at")
    op.drop_column("marketplace_deals", "dispute_reason")
