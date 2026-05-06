"""User ORM model — Telegram user with KYC and daily volume tracking."""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from db.models.base import Base


class User(Base):
    """Telegram user registered in the P2P bot."""

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

    # KYC / verification
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Trade Statistics
    total_trades: Mapped[int] = mapped_column(
        BigInteger, default=0, server_default="0", nullable=False
    )
    successful_trades: Mapped[int] = mapped_column(
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
