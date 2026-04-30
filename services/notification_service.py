"""Notification service for pushing Telegram messages to users."""

from __future__ import annotations

import structlog
from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from bot.keyboards import active_trade_maker_keyboard

log = structlog.get_logger(__name__)


async def notify_maker_taker_found(
    bot: Bot, maker_id: int, taker_username: str | None, order_id: str
) -> bool:
    """Notify the Maker that a Taker has accepted their order."""
    taker_display = f"@{taker_username}" if taker_username else "A user"
    
    text = (
        f"🔔 <b>Trade Started!</b>\n\n"
        f"Order: <code>{order_id[:8]}…</code>\n"
        f"Taker: {taker_display}\n\n"
        "Your crypto is locked in escrow. Wait for the taker to send the fiat payment.\n"
        "You will receive another notification once they confirm the transfer."
    )
    try:
        await bot.send_message(
            maker_id, 
            text, 
            parse_mode="HTML",
            reply_markup=active_trade_maker_keyboard(order_id)
        )
        return True
    except TelegramAPIError as e:
        log.error("notify_maker_taker_found_failed", maker_id=maker_id, error=str(e))
        return False


async def notify_maker_fiat_sent(
    bot: Bot, maker_id: int, order_id: str
) -> bool:
    """Notify the Maker that the Taker claims to have sent fiat."""
    text = (
        f"💸 <b>Fiat Transfer Confirmed by Taker!</b>\n\n"
        f"Order: <code>{order_id[:8]}…</code>\n\n"
        "Please check your bank account / wallet.\n"
        "If you received the exact amount, tap <b>Release Escrow</b>.\n"
        "If there is an issue, you can raise a dispute."
    )
    try:
        await bot.send_message(
            maker_id, 
            text, 
            parse_mode="HTML",
            reply_markup=active_trade_maker_keyboard(order_id)
        )
        return True
    except TelegramAPIError as e:
        log.error("notify_maker_fiat_sent_failed", maker_id=maker_id, error=str(e))
        return False
