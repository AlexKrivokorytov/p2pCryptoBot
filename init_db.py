"""One-shot database initializer.

Usage::

    python init_db.py

Creates all tables (idempotent) and seeds the master B2BLicense if none exists.
Safe to run multiple times — uses INSERT ... ON CONFLICT DO NOTHING patterns via
SQLAlchemy's idempotent ``create_all``.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import structlog
from dotenv import load_dotenv
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

load_dotenv()

from bot.config import settings  # noqa: E402  (must be after load_dotenv)
from db.models.b2b import B2BLicense  # noqa: E402
from db.models.base import Base  # noqa: E402
from db.models.user import User  # noqa: E402

log = structlog.get_logger(__name__)


async def _seed_master_user(session: AsyncSession) -> User:
    """Return existing admin user or create one if absent."""
    first_admin_id = next(iter(settings.ADMIN_IDS), 1)
    result = await session.execute(select(User).where(User.telegram_id == first_admin_id))
    admin = result.scalar_one_or_none()
    if admin is None:
        admin = User(
            telegram_id=first_admin_id,
            username=settings.MASTER_BOT_USERNAME,
            first_name="Admin",
            is_verified_seller=True,
        )
        session.add(admin)
        await session.flush()
        log.info("master_user_created", telegram_id=first_admin_id)
    return admin


async def _seed_master_license(session: AsyncSession, owner: User) -> None:
    """Create the master B2BLicense if none exists yet."""
    result = await session.execute(select(B2BLicense).limit(1))
    if result.scalar_one_or_none() is not None:
        log.info("master_license_already_exists")
        return

    license_ = B2BLicense(
        id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        owner_id=owner.telegram_id,
        telegram_payment_charge_id="INITIAL_FREE_LICENSE",
        expires_at=datetime.now(UTC) + timedelta(days=365 * 10),
        is_active=True,
        branding={
            "bot": {
                "name": "P2P Master Bot",
                "welcome_message": "Welcome to P2P Trading",
            }
        },
    )
    session.add(license_)
    log.info("master_license_created", license_id=str(license_.id))


async def init_db() -> None:
    """Initialize the database schema and seed essential data."""
    log.info("db_init_start", uri=settings.POSTGRES_URI.split("@")[-1])

    engine = create_async_engine(settings.POSTGRES_URI, echo=False)

    async with engine.begin() as conn:
        log.info("creating_tables")
        await conn.run_sync(Base.metadata.create_all)

    session_pool = async_sessionmaker(engine, expire_on_commit=False)
    async with session_pool() as session, session.begin():
        admin = await _seed_master_user(session)
        await _seed_master_license(session, admin)

    await engine.dispose()
    log.info("db_init_complete")


if __name__ == "__main__":
    asyncio.run(init_db())
