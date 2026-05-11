"""Service for administrative user management (search, verify)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.user import User
from services.admin_sandbox_service import log_admin_action


async def find_user_by_query(session: AsyncSession, query: str) -> User | None:
    """Search for a user by Telegram ID or Username."""
    if query.startswith("@"):
        username = query[1:]
        stmt = select(User).where(User.username == username)
    else:
        try:
            tg_id = int(query)
            stmt = select(User).where(User.telegram_id == tg_id)
        except ValueError:
            # Try username even without @ if it's not a number
            stmt = select(User).where(User.username == query)

    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def toggle_user_verification(
    session: AsyncSession, admin_id: int, user_id: int, is_verified: bool
) -> None:
    """Manually set user verification status and log the action."""
    stmt = select(User).where(User.telegram_id == user_id).with_for_update()
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if user:
        user.is_verified = is_verified
        await log_admin_action(
            session,
            admin_id=admin_id,
            action="toggle_verification",
            target_id=str(user_id),
            details={"is_verified": is_verified},
        )
        await session.commit()


def format_user_info(user: User) -> str:
    """Format user details for admin display."""
    status = "✅ Verified" if user.is_verified else "❌ Unverified"
    return (
        f"👤 <b>User Info</b>\n\n"
        f"ID: <code>{user.telegram_id}</code>\n"
        f"Username: @{user.username or '—'}\n"
        f"Name: {user.first_name or '—'}\n"
        f"Status: <b>{status}</b>\n\n"
        f"📊 <b>Stats</b>\n"
        f"Total Trades: <b>{user.total_trades}</b>\n"
        f"Successful: <b>{user.successful_trades}</b>"
    )
