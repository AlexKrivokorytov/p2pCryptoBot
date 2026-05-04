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
            maker_id, text, parse_mode="HTML", reply_markup=active_trade_maker_keyboard(order_id)
        )
        return True
    except TelegramAPIError as e:
        log.error("notify_maker_taker_found_failed", maker_id=maker_id, error=str(e))
        return False


async def notify_maker_fiat_sent(bot: Bot, maker_id: int, order_id: str) -> bool:
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
            maker_id, text, parse_mode="HTML", reply_markup=active_trade_maker_keyboard(order_id)
        )
        return True
    except TelegramAPIError as e:
        log.error("notify_maker_fiat_sent_failed", maker_id=maker_id, error=str(e))
        return False


async def notify_taker_escrow_released(
    bot: Bot, taker_id: int, order_id: str, asset: str, amount: float
) -> bool:
    """Notify the Taker that escrow has been released and crypto is on its way.

    Args:
        bot: Aiogram Bot instance.
        taker_id: Telegram ID of the taker.
        order_id: UUID string of the completed order.
        asset: Crypto asset ticker, e.g. "USDT".
        amount: Amount of crypto sent (after fees).

    Returns:
        True if message was sent, False on TelegramAPIError.
    """
    text = (
        f"✅ <b>Crypto Released!</b>\n\n"
        f"Order: <code>{order_id[:8]}…</code>\n"
        f"Amount: <code>{amount:.8g} {asset}</code>\n\n"
        "The seller confirmed your fiat payment. "
        "Your crypto has been transferred via Crypto Pay.\n"
        "Check your Crypto Pay wallet to confirm receipt."
    )
    try:
        await bot.send_message(taker_id, text, parse_mode="HTML")
        return True
    except TelegramAPIError as e:
        log.error("notify_taker_escrow_released_failed", taker_id=taker_id, error=str(e))
        return False


async def notify_dispute_opened(
    bot: Bot, maker_id: int, taker_id: int | None, order_id: str, reason: str
) -> None:
    """Notify both parties that a dispute has been opened on their trade.

    Args:
        bot: Aiogram Bot instance.
        maker_id: Telegram ID of the maker.
        taker_id: Telegram ID of the taker (may be None if trade not yet taken).
        order_id: UUID string of the disputed order.
        reason: The dispute reason submitted by the initiating party.
    """
    text = (
        f"⚠️ <b>Dispute Opened</b>\n\n"
        f"Order: <code>{order_id[:8]}…</code>\n"
        f"Reason: <i>{reason[:200]}</i>\n\n"
        "A moderator will review the trade chat history and make a decision. "
        "Please do not send any further payments. "
        "The funds are locked in escrow until the dispute is resolved."
    )
    for user_id in filter(None, [maker_id, taker_id]):
        try:
            await bot.send_message(user_id, text, parse_mode="HTML")
        except TelegramAPIError as e:
            log.error(
                "notify_dispute_opened_failed",
                user_id=user_id,
                order_id=order_id,
                error=str(e),
            )


async def notify_order_expired(bot: Bot, maker_id: int, order_id: str, asset: str) -> bool:
    """Notify the Maker that their ad has expired due to timeout.

    Args:
        bot: Aiogram Bot instance.
        maker_id: Telegram ID of the maker whose ad expired.
        order_id: UUID string of the expired order.
        asset: Crypto asset ticker of the ad.

    Returns:
        True if message was sent, False on TelegramAPIError.
    """
    text = (
        f"⏰ <b>Ad Expired</b>\n\n"
        f"Order: <code>{order_id[:8]}…</code>\n"
        f"Asset: <b>{asset}</b>\n\n"
        "Your ad was not taken within the time limit and has been cancelled.\n"
        "Your escrow funds have been automatically returned to your Crypto Pay wallet.\n\n"
        "You can create a new ad from the main menu."
    )
    try:
        await bot.send_message(maker_id, text, parse_mode="HTML")
        return True
    except TelegramAPIError as e:
        log.error("notify_order_expired_failed", maker_id=maker_id, error=str(e))
        return False
