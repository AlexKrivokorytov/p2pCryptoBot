"""User service for profile and statistics."""

from __future__ import annotations

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.user import User

log = structlog.get_logger(__name__)


async def get_user_profile(session: AsyncSession, telegram_id: int) -> User | None:
    """Retrieve user profile with statistics."""
    return await session.get(User, telegram_id)


async def get_or_create_user(
    session: AsyncSession,
    *,
    telegram_id: int,
    username: str | None = None,
    first_name: str | None = None,
) -> User:
    """Retrieve existing user or create a new one.

    Args:
        session: Active async SQLAlchemy session.
        telegram_id: Telegram ID of the user.
        username: Telegram username.
        first_name: Telegram first name.

    Returns:
        User model instance.
    """
    async with session.begin():
        from sqlalchemy import select

        result = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = result.scalar_one_or_none()
        if user is None:
            user = User(
                telegram_id=telegram_id,
                username=username,
                first_name=first_name,
            )
            session.add(user)
    return user


async def increment_user_trade_stats(
    session: AsyncSession, telegram_id: int, successful: bool = True
) -> None:
    """Increment trade statistics for a user.

    Uses pessimistic locking to ensure atomic updates under high concurrency.
    """
    from sqlalchemy import select

    stmt = select(User).where(User.telegram_id == telegram_id).with_for_update()
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        return

    user.total_trades += 1
    if successful:
        user.successful_trades += 1

    session.add(user)
    await session.flush()
    log.debug("user_stats_updated", telegram_id=telegram_id, successful=successful)
