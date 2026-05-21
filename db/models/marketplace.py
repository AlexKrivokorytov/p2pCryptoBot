"""Marketplace ORM models — Ads, Payment Methods, Reviews, Referrals, Appeals."""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import BigInteger, Boolean, DateTime, Enum, ForeignKey, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from db.models.base import Base


class AdType(StrEnum):
    """Type of the advertisement."""

    buy = "buy"  # Maker wants to buy crypto with fiat
    sell = "sell"  # Maker wants to sell crypto for fiat


class PriceType(StrEnum):
    """Type of pricing for the advertisement."""

    fixed = "fixed"  # Fixed fiat price per unit
    floating = "floating"  # Percentage offset from global spot price


class PaymentMethod(Base):
    """Standardized payment methods (e.g. Sber, Tinkoff, Revolut)."""

    __tablename__ = "payment_methods"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), nullable=False)  # e.g. RUB, USD, EUR
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class UserPaymentDetail(Base):
    """User's saved payment details (e.g. card numbers)."""

    __tablename__ = "user_payment_details"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.telegram_id", ondelete="CASCADE"), nullable=False
    )
    payment_method_id: Mapped[int] = mapped_column(
        ForeignKey("payment_methods.id", ondelete="CASCADE"), nullable=False
    )

    account_name: Mapped[str] = mapped_column(String(128), nullable=False)  # E.g. "Ivan Ivanov"
    account_number: Mapped[str] = mapped_column(String(128), nullable=False)  # E.g. "4276 1234 ..."
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Ad(Base):
    """P2P Advertisement created by a Maker."""

    __tablename__ = "ads"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    maker_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.telegram_id", ondelete="CASCADE"), nullable=False
    )

    type: Mapped[AdType] = mapped_column(Enum(AdType, create_type=False), nullable=False)
    asset: Mapped[str] = mapped_column(String(10), nullable=False)  # USDT, TON, BTC
    chain: Mapped[str] = mapped_column(String(50), nullable=True)  # ton, evm, tron, solana
    fiat: Mapped[str] = mapped_column(String(10), nullable=False)  # RUB, USD, EUR

    price_type: Mapped[PriceType] = mapped_column(
        Enum(PriceType, create_type=False), nullable=False
    )
    price_value: Mapped[float] = mapped_column(
        Numeric(precision=18, scale=2), nullable=False
    )  # Fixed price or % margin

    min_limit: Mapped[float] = mapped_column(
        Numeric(precision=18, scale=2), nullable=False
    )  # In Fiat
    max_limit: Mapped[float] = mapped_column(
        Numeric(precision=18, scale=2), nullable=False
    )  # In Fiat

    payment_method_ids: Mapped[str] = mapped_column(
        String(255), nullable=False
    )  # Comma-separated IDs
    terms: Mapped[str] = mapped_column(Text, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Review(Base):
    """User feedback after a completed trade."""

    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    reviewer_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.telegram_id", ondelete="CASCADE"), nullable=False
    )
    target_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.telegram_id", ondelete="CASCADE"), nullable=False
    )

    is_positive: Mapped[bool] = mapped_column(Boolean, nullable=False)
    comment: Mapped[str] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ReferralReward(Base):
    """Tracking of referral fees awarded to users."""

    __tablename__ = "referral_rewards"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    referrer_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.telegram_id", ondelete="CASCADE"), nullable=False
    )
    referred_user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.telegram_id", ondelete="SET NULL"), nullable=True
    )
    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orders.id", ondelete="SET NULL"), nullable=True
    )
    deal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("marketplace_deals.id", ondelete="SET NULL"), nullable=True
    )

    asset: Mapped[str] = mapped_column(String(10), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(precision=18, scale=6), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class DisputeTicket(Base):
    """Human appeal queue for unresolved disputes."""

    __tablename__ = "dispute_tickets"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    creator_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.telegram_id", ondelete="CASCADE"), nullable=False
    )
    moderator_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.telegram_id", ondelete="SET NULL"), nullable=True
    )

    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default="open", nullable=False
    )  # open, claimed, resolved
    resolution_notes: Mapped[str] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
