"""Profile handlers for viewing user statistics."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards import back_to_menu_keyboard
from services.user_service import get_user_profile

router = Router(name="profile")


def _build_profile_text(user: object | None) -> str:
    """Build the profile text string."""
    if not user:
        return "Profile not found."

    total = getattr(user, "total_trades", 0)
    successful = getattr(user, "successful_trades", 0)
    is_verified = getattr(user, "is_verified", False)
    telegram_id = getattr(user, "telegram_id", "?")
    success_rate = (successful / total * 100) if total > 0 else 0

    return (
        f"\U0001f464 <b>Your Profile</b>\n\n"
        f"ID: <code>{telegram_id}</code>\n"
        f"Status: {'\u2705 Verified' if is_verified else '\u274c Unverified'}\n\n"
        f"\U0001f4ca <b>Statistics</b>\n"
        f"Total Trades: <b>{total}</b>\n"
        f"Successful: <b>{successful}</b>\n"
        f"Success Rate: <b>{success_rate:.1f}%</b>\n"
    )


@router.message(Command("profile"))
async def cmd_profile(message: Message, session: AsyncSession) -> None:
    """Show the user profile via /profile command."""
    user = await get_user_profile(session, message.from_user.id)  # type: ignore[union-attr]
    text = _build_profile_text(user)
    await message.answer(text, reply_markup=back_to_menu_keyboard(), parse_mode="HTML")


@router.callback_query(F.data == "menu:profile")
async def cb_profile(callback: CallbackQuery, session: AsyncSession) -> None:
    """Show the user profile via inline button."""
    user = await get_user_profile(session, callback.from_user.id)  # type: ignore[union-attr]
    text = _build_profile_text(user)
    await callback.message.edit_text(  # type: ignore[union-attr]
        text, reply_markup=back_to_menu_keyboard(), parse_mode="HTML"
    )
    await callback.answer()
