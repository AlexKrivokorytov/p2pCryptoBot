"""Handlers for user settings and preferences (Phase 10)."""

from __future__ import annotations

import structlog
from aiogram import F, Router
from aiogram.types import CallbackQuery, Message
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards import fiat_selection_keyboard, settings_keyboard
from db.models.user import User

log = structlog.get_logger(__name__)
router = Router(name="settings")


@router.callback_query(F.data == "settings")
async def cb_settings(callback: CallbackQuery, db_user: User) -> None:
    """Show the settings main menu."""
    if not isinstance(callback.message, Message):
        return

    notif_status = "✅ Enabled" if db_user.notifications_enabled else "❌ Disabled"
    text = (
        "⚙️ <b>Settings & Preferences</b>\n\n"
        "Configure your trading experience:\n"
        f"• <b>Default Fiat:</b> {db_user.default_fiat}\n"
        f"• <b>Notifications:</b> {notif_status}\n"
    )

    await callback.message.edit_text(
        text,
        reply_markup=settings_keyboard(
            notifications_enabled=db_user.notifications_enabled,
            current_fiat=db_user.default_fiat,
        ),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "settings:toggle_notif")
async def cb_toggle_notif(callback: CallbackQuery, db_user: User, session: AsyncSession) -> None:
    """Toggle notification status for the user."""
    if not isinstance(callback.message, Message):
        return

    new_val = not db_user.notifications_enabled

    # Update in DB
    stmt = (
        update(User)
        .where(User.telegram_id == db_user.telegram_id)
        .values(notifications_enabled=new_val)
    )
    await session.execute(stmt)
    await session.commit()

    # Update local object for keyboard render
    db_user.notifications_enabled = new_val

    await callback.message.edit_text(
        callback.message.text or "",
        reply_markup=settings_keyboard(
            notifications_enabled=new_val,
            current_fiat=db_user.default_fiat,
        ),
        parse_mode="HTML",
    )
    await callback.answer(f"Notifications: {'ON' if new_val else 'OFF'}")


@router.callback_query(F.data == "settings:choose_fiat")
async def cb_choose_fiat(callback: CallbackQuery) -> None:
    """Show fiat selection menu."""
    if not isinstance(callback.message, Message):
        return

    await callback.message.edit_text(
        "💵 <b>Select Default Fiat Currency</b>\n\n"
        "This currency will be pre-selected when creating ads or browsing the market.",
        reply_markup=fiat_selection_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("settings:set_fiat:"))
async def cb_set_fiat(callback: CallbackQuery, db_user: User, session: AsyncSession) -> None:
    """Update default fiat currency in DB."""
    if not isinstance(callback.message, Message):
        return

    fiat = callback.data.split(":")[2]  # type: ignore[union-attr]

    stmt = update(User).where(User.telegram_id == db_user.telegram_id).values(default_fiat=fiat)
    await session.execute(stmt)
    await session.commit()

    db_user.default_fiat = fiat

    await callback.message.edit_text(
        f"✅ <b>Default Fiat set to {fiat}</b>",
        reply_markup=settings_keyboard(
            notifications_enabled=db_user.notifications_enabled,
            current_fiat=fiat,
        ),
        parse_mode="HTML",
    )
    await callback.answer()
