"""Start and main menu handlers."""

from __future__ import annotations

import structlog
from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import get_branding
from bot.keyboards import main_menu_keyboard

log = structlog.get_logger(__name__)
router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(message: Message, session: AsyncSession) -> None:
    """Handle /start — register user if new, show main menu."""
    tg_user = message.from_user
    if tg_user is None:
        return

    from services import user_service

    await user_service.get_or_create_user(
        session,
        telegram_id=tg_user.id,
        username=tg_user.username,
        first_name=tg_user.first_name,
    )

    log.info(
        "user_start",
        user_id=tg_user.id,
        step="cmd_start",
        status="ok",
    )
    b = get_branding()
    bot_name = b["bot"]["name"]
    welcome = b["bot"]["welcome_message"].format(
        bot_name=bot_name, first_name=tg_user.first_name or "trader"
    )
    await message.answer(
        welcome,
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
    b = get_branding()
    help_text = b["bot"]["help_text"].format(support_handle=b["bot"]["support_handle"])
    await callback.message.answer(  # type: ignore[union-attr]
        help_text,
        parse_mode="HTML",
    )
    await callback.answer()
