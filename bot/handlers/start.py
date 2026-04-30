"""Start and main menu handlers."""

from __future__ import annotations

import structlog
from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards import main_menu_keyboard
from db.models.user import User

log = structlog.get_logger(__name__)
router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(message: Message, session: AsyncSession) -> None:
    """Handle /start — register user if new, show main menu."""
    tg_user = message.from_user
    if tg_user is None:
        return

    async with session.begin():
        result = await session.execute(select(User).where(User.telegram_id == tg_user.id))
        user = result.scalar_one_or_none()
        if user is None:
            user = User(
                telegram_id=tg_user.id,
                username=tg_user.username,
                first_name=tg_user.first_name,
            )
            session.add(user)

    log.info(
        "user_start",
        user_id=tg_user.id,
        step="cmd_start",
        status="ok",
    )
    await message.answer(
        f"👋 Welcome to <b>P2P Exchange</b>, {tg_user.first_name or 'trader'}!\n\n"
        "Trade crypto peer-to-peer with escrow protection.",
        reply_markup=main_menu_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(lambda c: c.data == "menu:main")
async def cb_main_menu(callback: CallbackQuery) -> None:
    """Return to main menu."""
    await callback.message.edit_text(  # type: ignore[union-attr]
        "🏠 <b>Main Menu</b>",
        reply_markup=main_menu_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(lambda c: c.data == "help")
async def cb_help(callback: CallbackQuery) -> None:
    """Show help text."""
    await callback.message.answer(  # type: ignore[union-attr]
        "ℹ️ <b>How P2P works:</b>\n\n"
        "1️⃣ Create an order — choose asset, amount, and fiat currency.\n"
        "2️⃣ Pay the invoice via Crypto Pay — funds locked in escrow.\n"
        "3️⃣ Transfer fiat to the seller outside the bot.\n"
        "4️⃣ Seller confirms receipt → crypto released to you.\n"
        "5️⃣ Dispute? Open a case and a moderator will review.\n\n"
        "Questions? Contact @support",
        parse_mode="HTML",
    )
    await callback.answer()
