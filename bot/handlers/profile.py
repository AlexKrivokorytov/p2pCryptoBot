"""Profile handlers for viewing user statistics and reputation."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards import back_to_menu_keyboard
from services.marketplace_service import MarketplaceService
from services.user_service import get_or_create_user

router = Router(name="profile")


async def _build_profile_text(user: object | None, session: AsyncSession, bot_username: str) -> str:
    """Build the full profile text including reputation and referral info.

    Args:
        user: The User ORM object (or None).
        session: Async DB session.
        bot_username: Bot's Telegram username for referral link generation.

    Returns:
        Formatted HTML string.
    """
    if not user:
        return "❌ Profile not found."

    total = getattr(user, "total_trades", 0)
    successful = getattr(user, "successful_trades", 0)
    is_verified = getattr(user, "is_verified", False)
    telegram_id: int = getattr(user, "telegram_id", 0)
    success_rate = (successful / total * 100) if total > 0 else 0

    # Reputation from reviews
    rep = await MarketplaceService.get_user_reputation(session, telegram_id)
    rep_total = rep["total_reviews"]
    rep_positive = rep["positive_reviews"]
    rep_rate = rep["completion_rate"]

    # Referral link
    referral_link = f"https://t.me/{bot_username}?start=ref{telegram_id}"

    return (
        f"👤 <b>Your Profile</b>\n\n"
        f"ID: <code>{telegram_id}</code>\n"
        f"Status: {'✅ Verified' if is_verified else '❌ Unverified'}\n\n"
        f"📊 <b>Trade Statistics</b>\n"
        f"Total Trades: <b>{total}</b>\n"
        f"Successful: <b>{successful}</b>\n"
        f"Success Rate: <b>{success_rate:.1f}%</b>\n\n"
        f"⭐ <b>Reputation</b>\n"
        f"Reviews: <b>{rep_positive}/{rep_total} positive</b> ({rep_rate}%)\n\n"
        f"🔗 <b>Referral Program</b>\n"
        f"Your link: <code>{referral_link}</code>\n"
        f"Earn 20% of platform fees from your referrals' trades."
    )


@router.message(Command("profile"))
async def cmd_profile(message: Message, session: AsyncSession) -> None:
    """Show the user profile via /profile command."""
    if not message.from_user or not message.bot:
        return

    bot_me = await message.bot.get_me()

    # Use get_or_create to fix "Profile not found" if they haven't run /start
    user = await get_or_create_user(
        session,
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )

    text = await _build_profile_text(user, session, bot_me.username or "bot")
    await message.answer(text, reply_markup=back_to_menu_keyboard(), parse_mode="HTML")


@router.callback_query(F.data == "menu:profile")
async def cb_profile(callback: CallbackQuery, session: AsyncSession) -> None:
    """Show the user profile via inline button."""
    if not callback.from_user or not isinstance(callback.message, Message) or not callback.bot:
        return

    bot_me = await callback.bot.get_me()

    user = await get_or_create_user(
        session,
        telegram_id=callback.from_user.id,
        username=callback.from_user.username,
        first_name=callback.from_user.first_name,
    )

    text = await _build_profile_text(user, session, bot_me.username or "bot")
    await callback.message.edit_text(text, reply_markup=back_to_menu_keyboard(), parse_mode="HTML")
    await callback.answer()
