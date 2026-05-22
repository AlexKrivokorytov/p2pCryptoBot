"""Marketplace-specific push notifications via Telegram Bot.

These functions extend the existing notification_service.py patterns
to cover the Mini App marketplace deal lifecycle events.

All functions accept a ``Bot`` instance (not a singleton) so they
can be used from both the bot process and the API process via the
shared ``get_bot()`` factory in this module.

Integration pattern in api/main.py::

    from services.marketplace_notifications import get_bot, notify_deal_created
    bot = get_bot()
    asyncio.create_task(notify_deal_created(bot, deal, product))
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import structlog
from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.config import get_settings
from db.engine import async_session_factory
from db.models.notification import InAppNotification

if TYPE_CHECKING:
    from db.models.product import MarketplaceDeal

log = structlog.get_logger(__name__)
settings = get_settings()


async def _save_inapp_notification(user_id: int, type_: str, title: str, message: str) -> None:
    """Helper to save an in-app notification to the database."""
    try:
        async with async_session_factory() as session:
            notif = InAppNotification(
                user_id=user_id,
                type=type_,
                title=title,
                message=message,
                is_read=False,
            )
            session.add(notif)
            await session.commit()
    except Exception as exc:
        log.warning(
            "failed_to_save_inapp_notification", user_id=user_id, type=type_, error=str(exc)
        )


# ── Bot factory ───────────────────────────────────────────────────────────────

_bot_instance: Bot | None = None


def get_bot() -> Bot:
    """Return a shared Bot instance for sending notifications from the API process.

    The instance is created lazily on first call and reused afterwards.
    This avoids creating a new HTTP session per request.

    Returns:
        Configured aiogram Bot instance.
    """
    global _bot_instance
    if _bot_instance is None:
        _bot_instance = Bot(token=settings.BOT_TOKEN)
    return _bot_instance


# ── Internal helpers ──────────────────────────────────────────────────────────


async def _safe_send(
    bot: Bot,
    user_id: int,
    text: str,
    *,
    event: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> bool:
    """Send a Telegram message, logging failures without raising.

    Args:
        bot: Bot instance.
        user_id: Telegram user ID to send to.
        text: HTML-formatted message text.
        event: Stable event name for structured logging.
        reply_markup: Optional inline keyboard.

    Returns:
        True if sent successfully, False on Telegram API error.
    """
    try:
        await bot.send_message(user_id, text, parse_mode="HTML", reply_markup=reply_markup)
        log.info(event, user_id=user_id, status="sent")
        return True
    except TelegramAPIError as exc:
        log.error(event, user_id=user_id, error=str(exc), status="failed")
        return False


def _deal_link(deal_id: str) -> str:
    """Format a short deal reference for messages."""
    return f"<code>{deal_id[:8].upper()}</code>"


def _deal_keyboard(deal_id: str) -> InlineKeyboardMarkup:
    """Create an inline keyboard linking to the Mini App deal page."""
    # Note: startapp doesn't support hyphens, so we strip them
    clean_id = deal_id.replace("-", "")
    url = f"https://t.me/{settings.MASTER_BOT_USERNAME}/app?startapp=deal_{clean_id}"
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Open Deal in App", url=url)]]
    )


# ── Marketplace notifications ─────────────────────────────────────────────────


async def notify_deal_created(
    bot: Bot,
    seller_id: int,
    buyer_first_name: str,
    deal_id: str,
    product_title: str,
    amount: float,
    currency: str,
) -> bool:
    """Notify the seller that a new deal has been opened on their product.

    Args:
        bot: Bot instance.
        seller_id: Telegram user ID of the seller.
        buyer_first_name: Display name of the buyer.
        deal_id: UUID string of the deal.
        product_title: Title of the purchased product.
        amount: Deal amount.
        currency: Currency type label (XTR / USD / TON etc.).

    Returns:
        True if the notification was sent successfully.
    """
    text = (
        f"🛒 <b>New Order!</b>\n\n"
        f"Someone purchased <b>{product_title}</b>\n"
        f"Deal ID: <code>{deal_id}</code>\n"
        f"Buyer: {buyer_first_name}\n"
        f"Amount: {amount} {currency}\n\n"
        f"Please check the deal page."
    )

    await _save_inapp_notification(
        user_id=seller_id,
        type_="deal_created",
        title="New Order",
        message=f"Someone purchased {product_title} for {amount} {currency}.",
    )

    return await _safe_send(
        bot, seller_id, text, event="notify_deal_created", reply_markup=_deal_keyboard(deal_id)
    )


async def notify_deal_paid(
    bot: Bot,
    seller_id: int,
    deal_id: str,
    product_title: str,
    amount: float,
    currency: str,
) -> bool:
    """Notify the seller that the buyer claims to have sent fiat payment.

    Args:
        bot: Bot instance.
        seller_id: Telegram user ID of the seller.
        deal_id: UUID string of the deal.
        product_title: Title of the purchased product.
        amount: Deal amount.
        currency: Currency type label.

    Returns:
        True if the notification was sent successfully.
    """
    text = (
        f"✅ <b>Deal Paid!</b>\n\n"
        f"The buyer has confirmed payment for Deal <code>{deal_id}</code>.\n\n"
        f"Please verify receipt and release the funds/digital goods."
    )

    await _save_inapp_notification(
        user_id=seller_id,
        type_="deal_paid",
        title="Deal Paid",
        message=f"The buyer has confirmed payment for Deal {deal_id}. Please verify receipt.",
    )

    return await _safe_send(
        bot, seller_id, text, event="notify_deal_paid", reply_markup=_deal_keyboard(deal_id)
    )


async def notify_deal_delivered(
    bot: Bot,
    buyer_id: int,
    deal_id: str,
    product_title: str,
) -> bool:
    """Notify the buyer that the seller confirmed delivery.

    Args:
        bot: Bot instance.
        buyer_id: Telegram user ID of the buyer.
        deal_id: UUID string of the deal.
        product_title: Title of the purchased product.

    Returns:
        True if the notification was sent successfully.
    """
    text = (
        f"📦 <b>Deal Delivered!</b>\n\n"
        f"The seller has released the goods/escrow for Deal <code>{deal_id}</code>.\n\n"
        f"Please confirm everything is okay to complete the deal."
    )

    await _save_inapp_notification(
        user_id=buyer_id,
        type_="deal_delivered",
        title="Deal Delivered",
        message=f"The seller has released the goods/escrow for Deal {deal_id}.",
    )

    return await _safe_send(
        bot, buyer_id, text, event="notify_deal_delivered", reply_markup=_deal_keyboard(deal_id)
    )


async def notify_deal_completed(
    bot: Bot,
    seller_id: int,
    deal_id: str,
    product_title: str,
) -> bool:
    """Notify the seller that the buyer confirmed receipt and deal is complete.

    Args:
        bot: Bot instance.
        seller_id: Telegram user ID of the seller.
        deal_id: UUID string of the deal.
        product_title: Title of the purchased product.

    Returns:
        True if the notification was sent successfully.
    """
    text = (
        f"🎉 <b>Deal Completed!</b>\n\n"
        f"Buyer confirmed receipt for <b>{product_title}</b>\n"
        f"Deal: {_deal_link(deal_id)}\n\n"
        f"Funds have been released! ⭐"
    )
    return await _safe_send(
        bot, seller_id, text, event="notify_deal_completed", reply_markup=_deal_keyboard(deal_id)
    )


async def notify_stars_purchase(
    bot: Bot,
    seller_id: int,
    buyer_first_name: str,
    deal_id: str,
    product_title: str,
    stars: float,
) -> bool:
    """Notify the seller of an instant Telegram Stars purchase.

    Stars purchases are auto-completed so there is no escrow wait.

    Args:
        bot: Bot instance.
        seller_id: Telegram user ID of the seller.
        buyer_first_name: Display name of the buyer.
        deal_id: UUID string of the deal.
        product_title: Title of the purchased product.
        stars: Number of Stars paid.

    Returns:
        True if the notification was sent successfully.
    """
    text = (
        f"⭐ <b>Stars Purchase!</b>\n\n"
        f"{buyer_first_name} bought <b>{product_title}</b>\n"
        f"Deal: {_deal_link(deal_id)}\n"
        f"Received: <code>{int(stars)} Stars</code>\n\n"
        f"💰 Payment is instant — no escrow needed."
    )
    return await _safe_send(
        bot, seller_id, text, event="notify_stars_purchase", reply_markup=_deal_keyboard(deal_id)
    )


async def notify_deal_cancelled(
    bot: Bot,
    seller_id: int,
    buyer_id: int,
    deal_id: str,
    product_title: str,
    reason: str = "Timeout or user cancelled",
) -> None:
    """Notify both parties that a deal was cancelled.

    Args:
        bot: Bot instance.
        seller_id: Telegram user ID of the seller.
        buyer_id: Telegram user ID of the buyer.
        deal_id: UUID string of the deal.
        product_title: Title of the product.
        reason: Human-readable cancellation reason.
    """
    text = (
        f"❌ <b>Deal Cancelled</b>\n\n"
        f"Deal for <b>{product_title}</b> was cancelled.\n"
        f"Deal: {_deal_link(deal_id)}\n"
        f"Reason: {reason}"
    )
    results = await asyncio.gather(
        _safe_send(bot, seller_id, text, event="notify_deal_cancelled_seller"),
        _safe_send(bot, buyer_id, text, event="notify_deal_cancelled_buyer"),
        return_exceptions=True,
    )
    for r in results:
        if isinstance(r, Exception):
            log.error("notify_deal_cancelled_error", deal_id=deal_id, error=str(r))


async def notify_new_message(
    bot: Bot,
    recipient_id: int,
    sender_name: str,
    deal_id: str,
    product_title: str,
) -> bool:
    """Notify a deal participant that they received a new chat message.

    Args:
        bot: Bot instance.
        recipient_id: Telegram user ID to notify.
        sender_name: Display name of the message sender.
        deal_id: UUID string of the deal.
        product_title: Title of the product in the deal.

    Returns:
        True if the notification was sent successfully.
    """
    text = (
        f"💬 <b>New Message</b>\n\n"
        f"{sender_name} sent a message about <b>{product_title}</b>\n"
        f"Deal: {_deal_link(deal_id)}\n\n"
        f"Open the Mini App to reply."
    )
    return await _safe_send(bot, recipient_id, text, event="notify_new_message")


async def notify_dispute_opened(
    bot: Bot,
    buyer_id: int,
    seller_id: int,
    deal_id: str,
    reason: str,
) -> None:
    """Notify both deal parties that a dispute has been opened.

    Args:
        bot: Bot instance.
        buyer_id: Telegram user ID of the buyer.
        seller_id: Telegram user ID of the seller.
        deal_id: UUID string of the deal.
        reason: Dispute reason text.
    """
    text = (
        f"⚠️ <b>Dispute Opened</b>\n\n"
        f"Deal: {_deal_link(deal_id)}\n"
        f"Reason: <i>{reason}</i>\n\n"
        f"An admin will review the case and make a decision. "
        f"Please do not send any additional payments."
    )
    results = await asyncio.gather(
        _safe_send(bot, buyer_id, text, event="notify_dispute_opened_buyer"),
        _safe_send(bot, seller_id, text, event="notify_dispute_opened_seller"),
        return_exceptions=True,
    )
    for r in results:
        if isinstance(r, Exception):
            log.error("notify_dispute_opened_error", deal_id=deal_id, error=str(r))


async def notify_marketplace_admin_dispute(
    bot: Bot,
    *,
    deal_id: str,
    initiator_id: int,
    initiator_role: str,
    amount: float,
    currency: str,
    reason: str,
) -> None:
    """Send a dispute alert to the configured admin chat/group.

    Sends inline buttons for quick resolution via the bot.

    Args:
        bot: Bot instance.
        deal_id: UUID string of the deal.
        initiator_id: Telegram user ID of whoever opened the dispute.
        initiator_role: ``"buyer"`` or ``"seller"``.
        amount: Deal amount.
        currency: Currency label (XTR / USDT / TON etc.).
        reason: Dispute reason text.
    """
    from bot.config import settings

    admin_chat_id = getattr(settings, "ADMIN_CHAT_ID", None)
    if not admin_chat_id:
        log.warning(
            "notify_marketplace_admin_dispute_skipped",
            reason="ADMIN_CHAT_ID not configured",
        )
        return

    from aiogram.types import InlineKeyboardButton
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    short_id = deal_id[:8].upper()
    text = (
        f"🚨 <b>NEW MARKETPLACE DISPUTE</b>\n\n"
        f"Deal: <code>{short_id}</code>\n"
        f"Initiator: <code>{initiator_id}</code> ({initiator_role})\n"
        f"Amount: <code>{amount} {currency}</code>\n"
        f"Reason: <i>{reason}</i>"
    )
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="💰 Release to Seller",
            callback_data=f"mkt:dispute:resolve:{deal_id}:seller",
        ),
        InlineKeyboardButton(
            text="🔄 Refund to Buyer",
            callback_data=f"mkt:dispute:resolve:{deal_id}:buyer",
        ),
    )
    try:
        await bot.send_message(
            admin_chat_id,
            text,
            reply_markup=builder.as_markup(),
            parse_mode="HTML",
        )
        log.info("notify_marketplace_admin_dispute_sent", deal_id=deal_id)
    except Exception as exc:
        log.error("notify_marketplace_admin_dispute_failed", deal_id=deal_id, error=str(exc))


async def notify_dispute_resolved(
    bot: Bot,
    *,
    buyer_id: int,
    seller_id: int,
    deal_id: str,
    resolution: str,
    comment: str = "",
) -> None:
    """Notify both deal parties of the admin's dispute resolution decision.

    Args:
        bot: Bot instance.
        buyer_id: Telegram user ID of the buyer.
        seller_id: Telegram user ID of the seller.
        deal_id: UUID string of the deal.
        resolution: ``"buyer"`` or ``"seller"``.
        comment: Optional admin comment to include in the notification.
    """
    import asyncio

    if resolution == "seller":
        decision_text = "✅ Funds have been <b>released to the seller</b>."
    else:
        decision_text = "🔄 Funds have been <b>refunded to the buyer</b>."

    comment_line = f"\nAdmin note: <i>{comment}</i>" if comment else ""
    text = (
        f"⚖️ <b>Dispute Resolved</b>\n\nDeal: {_deal_link(deal_id)}\n{decision_text}{comment_line}"
    )
    results = await asyncio.gather(
        _safe_send(bot, buyer_id, text, event="notify_dispute_resolved_buyer"),
        _safe_send(bot, seller_id, text, event="notify_dispute_resolved_seller"),
        return_exceptions=True,
    )
    for r in results:
        if isinstance(r, Exception):
            log.error("notify_dispute_resolved_error", deal_id=deal_id, error=str(r))


async def notify_seller_payout_sent(bot: Bot, deal: MarketplaceDeal) -> bool:
    """Notify the seller that a payout was successfully sent on-chain.

    Args:
        bot: Bot instance.
        deal: The MarketplaceDeal that was paid out.

    Returns:
        True if the notification was sent successfully.
    """
    deal_id = str(deal.id)
    short_tx = deal.tx_hash_release[:8] + "..." if deal.tx_hash_release else "unknown"
    text = (
        f"🏁 <b>Deal Completed!</b>\n\n"
        f"Deal <code>{deal_id}</code> has been successfully completed.\n"
        f"TX: <code>{short_tx}</code>\n\n"
        f"Funds are released. Thank you for using the marketplace!"
    )

    await _save_inapp_notification(
        user_id=deal.buyer_id,
        type_="deal_completed",
        title="Deal Completed",
        message=f"Deal {deal_id} has been successfully completed.",
    )
    await _save_inapp_notification(
        user_id=deal.seller_id,
        type_="deal_completed",
        title="Deal Completed",
        message=f"Deal {deal_id} has been successfully completed. Funds are released.",
    )

    return await _safe_send(bot, deal.seller_id, text, event="notify_seller_payout_sent")
