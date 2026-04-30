"""wallets — adds user_wallets table with wallet_chain ENUM

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-28

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Idempotent type creation — safe to run multiple times
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'wallet_chain') THEN
                CREATE TYPE wallet_chain AS ENUM ('ton', 'evm');
            END IF;
        END
        $$;
    """)

    op.create_table(
        'user_wallets',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('chain', sa.String(10), nullable=False),
        sa.Column('address', sa.String(length=256), nullable=False),
        sa.Column('encrypted_private_key', sa.String(length=1024), nullable=False),
        sa.Column('encrypted_mnemonic', sa.String(length=2048), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['user_id'], ['users.telegram_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('address'),
    )
    op.create_index('ix_user_wallets_user_id', 'user_wallets', ['user_id'], unique=False)
    # Cast the VARCHAR column to the native ENUM type now that it exists
    op.execute("ALTER TABLE user_wallets ALTER COLUMN chain TYPE wallet_chain USING chain::wallet_chain")


def downgrade() -> None:
    op.drop_index('ix_user_wallets_user_id', table_name='user_wallets')
    op.drop_table('user_wallets')
    op.execute('DROP TYPE IF EXISTS wallet_chain')
