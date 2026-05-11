from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.models.base import Base

if TYPE_CHECKING:
    from db.models.user import User


class B2BLicense(Base):
    """White-label license for B2B clients."""

    __tablename__ = "b2b_licenses"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.telegram_id"), nullable=False
    )

    # License Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Payment details (Stars)
    telegram_payment_charge_id: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=True
    )

    # Branding & Customization
    branding: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, server_default="{}", nullable=False
    )

    # Multi-bot management
    bot_token_encrypted: Mapped[str] = mapped_column(String(512), nullable=True)

    # Infrastructure
    spend_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), default=uuid.uuid4, unique=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )

    # Relationships
    owner: Mapped[User] = relationship("User")

    def __repr__(self) -> str:
        return f"<B2BLicense id={self.id} owner_id={self.owner_id} active={self.is_active}>"


class TONInvoice(Base):
    """Invoice for B2B licenses paid via TON (Phase 4)."""

    __tablename__ = "ton_invoices"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.telegram_id"), nullable=False
    )

    amount_ton: Mapped[float] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False
    )  # pending, paid, expired

    # The memo used to match incoming TON transaction
    memo: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)

    tx_hash: Mapped[str] = mapped_column(String(128), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    paid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<TONInvoice id={self.id} amount={self.amount_ton} status={self.status}>"
