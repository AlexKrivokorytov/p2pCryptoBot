"""Order ORM model — core entity for the P2P deal lifecycle."""

import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.models.base import Base


class OrderType(enum.StrEnum):
    """Direction of the P2P trade from the Maker's perspective."""

    sell_crypto = "sell_crypto"  # Maker sells crypto, receives fiat
    buy_crypto = "buy_crypto"  # Maker buys crypto, sends fiat


class OrderStatus(enum.StrEnum):
    """Lifecycle states for a P2P order."""

    pending_funding = "pending_funding"  # Invoice created, Maker must pay to fund escrow
    active = "active"  # Funded, visible in Order Book
    escrow_held = "escrow_held"  # Taker accepted, fiat being transferred
    completed = "completed"  # Fiat confirmed, crypto released
    dispute = "dispute"  # Parties disagree, locked for review
    cancelled = "cancelled"  # Timed-out or user-cancelled


class SupportedAsset(enum.StrEnum):
    """Allowed crypto assets for P2P trading."""

    BTC = "BTC"
    TON = "TON"
    USDT = "USDT"
    USDC = "USDC"
    ETH = "ETH"


class Order(Base):
    """P2P trading order with escrow lifecycle.

    Maker creates the ad and funds the escrow via Crypto Pay invoice.
    Taker accepts the ad from the Order Book and completes fiat transfer.
    """

    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Participants
    maker_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.telegram_id"), nullable=False, index=True
    )
    taker_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.telegram_id"), nullable=True, index=True
    )

    # Trade direction
    order_type: Mapped[str] = mapped_column(Enum(OrderType, name="order_type"), nullable=False)

    # Trade details
    asset: Mapped[str] = mapped_column(Enum(SupportedAsset, name="supported_asset"), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(precision=18, scale=8), nullable=False)
    fiat_amount: Mapped[Decimal] = mapped_column(Numeric(precision=18, scale=2), nullable=False)
    fiat_currency: Mapped[str] = mapped_column(String(10), nullable=False)

    # Payment method for fiat (e.g. "Sberbank", "Revolut", "SWIFT")
    payment_method: Mapped[str] = mapped_column(String(64), nullable=False, default="Any")

    # Status
    status: Mapped[str] = mapped_column(
        Enum(OrderStatus, name="order_status"),
        nullable=False,
        default=OrderStatus.pending_funding,
        index=True,
    )
    fiat_confirmed: Mapped[bool] = mapped_column(default=False, nullable=False)

    # Crypto Pay integration
    invoice_id: Mapped[str] = mapped_column(String(128), nullable=True, unique=True)
    spend_id: Mapped[str] = mapped_column(String(128), nullable=True, unique=True)
    crypto_pay_payload: Mapped[str] = mapped_column(Text, nullable=True)
    payment_url: Mapped[str] = mapped_column(Text, nullable=True)

    # Fee details
    fee_percent: Mapped[Decimal] = mapped_column(
        Numeric(6, 4), default=Decimal("0.0"), nullable=False
    )
    fee_fixed: Mapped[Decimal] = mapped_column(
        Numeric(18, 8), default=Decimal("0.0"), nullable=False
    )
    total_fee: Mapped[Decimal] = mapped_column(
        Numeric(18, 8), default=Decimal("0.0"), nullable=False
    )

    # Optional dispute reason
    dispute_reason: Mapped[str] = mapped_column(Text, nullable=True)

    # On-chain Escrow
    escrow_wallet_address: Mapped[str] = mapped_column(String(255), nullable=True, index=True)
    escrow_wallet_private_key_enc: Mapped[str] = mapped_column(String(512), nullable=True)
    on_chain_tx_hash: Mapped[str] = mapped_column(String(255), nullable=True, index=True)
    on_chain_status: Mapped[str] = mapped_column(String(50), nullable=False, default="none")
    on_chain_gas_buffer: Mapped[Decimal] = mapped_column(
        Numeric(18, 8), default=Decimal("0.0"), nullable=False
    )

    # Relationships
    maker: Mapped["User"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "User", foreign_keys=[maker_id], lazy="selectin"
    )
    taker: Mapped["User"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "User", foreign_keys=[taker_id], lazy="selectin"
    )

    def __repr__(self) -> str:
        return (
            f"<Order id={self.id} type={self.order_type} asset={self.asset} status={self.status}>"
        )
