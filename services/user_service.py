"""User service for profile and statistics."""

from __future__ import annotations

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.user import User

log = structlog.get_logger(__name__)


async def get_user_profile(session: AsyncSession, telegram_id: int) -> User | None:
    """Retrieve user profile with statistics."""
    return await session.get(User, telegram_id)


async def increment_user_trade_stats(
    session: AsyncSession, telegram_id: int, successful: bool = True
) -> None:
    """Increment trade statistics for a user."""
    user = await session.get(User, telegram_id)
    if not user:
        return

    user.total_trades += 1
    if successful:
        user.successful_trades += 1

    session.add(user)
    await session.flush()
    log.debug("user_stats_updated", telegram_id=telegram_id, successful=successful)
