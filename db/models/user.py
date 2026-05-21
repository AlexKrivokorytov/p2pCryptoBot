"""User ORM model — Telegram user with KYC and daily volume tracking."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, DateTime, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.models.base import Base


class User(Base):
    """Telegram user registered in the P2P bot."""

    # New relationship
    notifications: Mapped[list["InAppNotification"]] = relationship("InAppNotification", back_populates="user")

    __tablename__ = "users"

    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), nullable=True)
    first_name: Mapped[str] = mapped_column(String(128), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Preferences & Referrals
    language_code: Mapped[str] = mapped_column(
        String(10), default="en", server_default="en", nullable=False
    )
    referred_by_id: Mapped[int] = mapped_column(BigInteger, nullable=True)
    referral_balance: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2), default=Decimal("0.00"), server_default="0.00", nullable=False
    )

    default_fiat: Mapped[str] = mapped_column(
        String(10), default="USD", server_default="USD", nullable=False
    )
    notifications_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False
    )

    # KYC / verification
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_verified_seller: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    is_shadowbanned: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    dispute_count_buyer: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0", nullable=False)
    dispute_count_seller: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0", nullable=False)
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Trade Statistics
    total_trades: Mapped[int] = mapped_column(
        BigInteger, default=0, server_default="0", nullable=False
    )
    successful_trades: Mapped[int] = mapped_column(
        BigInteger, default=0, server_default="0", nullable=False
    )

    # Reviews
    rating_sum: Mapped[int] = mapped_column(
        BigInteger, default=0, server_default="0", nullable=False
    )
    review_count: Mapped[int] = mapped_column(
        BigInteger, default=0, server_default="0", nullable=False
    )

    # Daily volume cap tracking (reset daily via cleanup task)
    daily_volume_usdt: Mapped[float] = mapped_column(
        Numeric(precision=18, scale=2), default=0.0, nullable=False
    )
    daily_volume_reset_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    # Encrypted exchange API keys (AES-256-GCM, stored as hex)
    binance_api_key_enc: Mapped[str] = mapped_column(String(512), nullable=True)
    binance_api_secret_enc: Mapped[str] = mapped_column(String(512), nullable=True)
    okx_api_key_enc: Mapped[str] = mapped_column(String(512), nullable=True)
    okx_api_secret_enc: Mapped[str] = mapped_column(String(512), nullable=True)
    bybit_api_key_enc: Mapped[str] = mapped_column(String(512), nullable=True)
    bybit_api_secret_enc: Mapped[str] = mapped_column(String(512), nullable=True)

    def __repr__(self) -> str:
        return f"<User telegram_id={self.telegram_id} username={self.username}>"
