"""Profile handlers for viewing user statistics and reputation."""

from __future__ import annotations

from typing import Any

from aiogram import Bot, F, Router
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
    """Show the user's profile."""
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


@router.message(Command("referral"))
async def cmd_referral(message: Message, session: AsyncSession) -> None:
    """Show the referral program dashboard."""
    if not message.from_user or not message.bot:
        return

    await _show_referral_dashboard(message, session, message.bot, edit=False)


@router.callback_query(F.data == "menu:referral")
async def cb_referral(callback: CallbackQuery, session: AsyncSession) -> None:
    """Show the referral program dashboard via inline button."""
    if not callback.from_user or not isinstance(callback.message, Message) or not callback.bot:
        return

    await _show_referral_dashboard(
        callback.message, session, callback.bot, edit=True, user=callback.from_user
    )
    await callback.answer()


async def _show_referral_dashboard(
    message: Message, session: AsyncSession, bot: Bot, edit: bool = False, user: Any = None
) -> None:
    bot_me = await bot.get_me()
    target_user = user or message.from_user
    if not target_user:
        return

    db_user = await get_or_create_user(
        session,
        telegram_id=target_user.id,
        username=target_user.username,
        first_name=target_user.first_name,
    )

    from sqlalchemy import func, select

    from db.models.marketplace import ReferralReward
    from db.models.user import User as DBUser

    # Get referral count
    count_stmt = (
        select(func.count()).select_from(DBUser).where(DBUser.referred_by_id == target_user.id)
    )
    count_result = await session.execute(count_stmt)
    referral_count = count_result.scalar_one_or_none() or 0

    # Get total rewards earned
    sum_stmt = select(func.sum(ReferralReward.amount)).where(
        ReferralReward.referrer_id == target_user.id
    )
    sum_result = await session.execute(sum_stmt)
    total_earned = sum_result.scalar_one_or_none() or 0

    referral_link = f"https://t.me/{bot_me.username}?start=ref{target_user.id}"
    balance = getattr(db_user, "referral_balance", 0)

    text = (
        f"🎁 <b>Referral Program</b>\n\n"
        f"Invite friends and earn <b>20%</b> of their trading fees for life!\n\n"
        f"🔗 <b>Your Link:</b>\n<code>{referral_link}</code>\n\n"
        f"👥 <b>Total Referrals:</b> {referral_count}\n"
        f"💰 <b>Current Balance:</b> {balance:.4f} USDT\n"
        f"🏆 <b>Total Earned:</b> {total_earned:.4f} USDT\n\n"
        f"<i>Your referral balance is automatically credited "
        f"when your referrals complete trades.</i>"
    )

    from bot.keyboards import referral_dashboard_keyboard

    if edit:
        await message.edit_text(text, reply_markup=referral_dashboard_keyboard(), parse_mode="HTML")
    else:
        await message.answer(text, reply_markup=referral_dashboard_keyboard(), parse_mode="HTML")
