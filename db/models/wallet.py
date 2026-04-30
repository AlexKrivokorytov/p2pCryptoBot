"""UserWallet model — stores encrypted on-chain wallet addresses per user."""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from db.models.base import Base


class WalletChain(enum.StrEnum):
    """Supported blockchain networks.

    Values match the ``wallet_chain`` Postgres ENUM type created in migration 0005.
    """

    ton = "ton"
    evm = "evm"


class UserWallet(Base):
    """An on-chain wallet address generated for a specific user.

    The ``chain`` column is stored as ``VARCHAR(10)`` at the DB level and cast
    to the ``wallet_chain`` Postgres ENUM via the migration (0005_wallets).
    Using ``String`` in SQLAlchemy avoids the ``create_type`` auto-emit issue
    with psycopg2/Alembic sync context.
    """

    __tablename__ = "user_wallets"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        index=True,
    )
    # Stored as wallet_chain ENUM at DB level; mapped as String for ORM compatibility
    chain: Mapped[str] = mapped_column(String(10), nullable=False)
    address: Mapped[str] = mapped_column(String(256), nullable=False, unique=True)

    # AES-256-GCM encrypted private key stored as hex string (nonce + ciphertext)
    encrypted_private_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    # Encrypted mnemonic phrase (optional — not all chains use mnemonics)
    encrypted_mnemonic: Mapped[str] = mapped_column(String(2048), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<UserWallet user_id={self.user_id} chain={self.chain} address={self.address[:12]}…>"
        )
