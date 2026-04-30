"""chat

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-28

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PGUUID

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chat_messages",
        sa.Column(
            "id", PGUUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("order_id", PGUUID(as_uuid=True), nullable=False),
        sa.Column("sender_id", sa.BigInteger(), nullable=False),
        sa.Column("message_text", sa.Text(), nullable=True),
        sa.Column("photo_file_id", sa.String(length=256), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sender_id"], ["users.telegram_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_chat_messages_order_id"), "chat_messages", ["order_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_chat_messages_order_id"), table_name="chat_messages")
    op.drop_table("chat_messages")
