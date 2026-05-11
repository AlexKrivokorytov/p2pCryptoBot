import structlog
from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from bot.config import get_branding
from bot.keyboards import active_trade_maker_keyboard

log = structlog.get_logger(__name__)


async def notify_maker_taker_found(
    bot: Bot, maker_id: int, taker_username: str | None, order_id: str
) -> bool:
    """Notify the Maker that a Taker has accepted their order."""
    branding = get_branding()
    taker_display = f"@{taker_username}" if taker_username else "A user"
    template = branding["notifications"]["taker_found"]

    text = template.format(
        order_id=order_id, order_id_short=order_id[:8], taker_display=taker_display
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
    branding = get_branding()
    template = branding["notifications"]["fiat_sent"]

    text = template.format(order_id=order_id, order_id_short=order_id[:8])
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
    """Notify the Taker that escrow has been released and crypto is on its way."""
    branding = get_branding()
    template = branding["notifications"]["escrow_released"]

    text = template.format(
        order_id=order_id,
        order_id_short=order_id[:8],
        asset=asset,
        amount=f"{amount:.8g}",
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
    """Notify both parties that a dispute has been opened on their trade."""
    branding = get_branding()
    template = branding["notifications"]["dispute_opened"]

    text = template.format(
        order_id=order_id,
        order_id_short=order_id[:8],
        reason=reason[:200],
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


async def notify_dispute_resolved(
    bot: Bot,
    maker_id: int,
    taker_id: int | None,
    order_id: str,
    decision: str,
    status: str,
) -> None:
    """Notify both parties that a dispute has been resolved.

    Args:
        bot: Bot instance.
        maker_id: Maker TG ID.
        taker_id: Taker TG ID.
        order_id: UUID string.
        decision: Decision label (e.g. 'taker_wins').
        status: Final order status (e.g. 'completed').
    """
    branding = get_branding()
    template = branding["notifications"]["dispute_resolved"]

    text = template.format(
        order_id=order_id,
        order_id_short=order_id[:8],
        decision=decision.replace("_", " ").title(),
        status=status.title(),
    )
    for user_id in filter(None, [maker_id, taker_id]):
        try:
            await bot.send_message(user_id, text, parse_mode="HTML")
        except TelegramAPIError as e:
            log.error("notify_dispute_resolved_failed", user_id=user_id, error=str(e))


async def notify_order_expired(bot: Bot, maker_id: int, order_id: str, asset: str) -> bool:
    """Notify the Maker that their ad has expired due to timeout."""
    branding = get_branding()
    template = branding["notifications"]["order_expired"]

    text = template.format(
        order_id=order_id,
        order_id_short=order_id[:8],
        asset=asset,
    )
    try:
        await bot.send_message(maker_id, text, parse_mode="HTML")
        return True
    except TelegramAPIError as e:
        log.error("notify_order_expired_failed", maker_id=maker_id, error=str(e))
        return False


async def notify_escrow_refunded(
    bot: Bot, maker_id: int, order_id: str, asset: str, amount: float
) -> bool:
    """Notify the Maker that their escrow has been refunded."""
    branding = get_branding()
    template = branding["notifications"]["escrow_refunded"]

    text = template.format(
        order_id=order_id,
        order_id_short=order_id[:8],
        asset=asset,
        amount=f"{amount:.8g}",
    )
    try:
        await bot.send_message(maker_id, text, parse_mode="HTML")
        return True
    except TelegramAPIError as e:
        log.error("notify_escrow_refunded_failed", maker_id=maker_id, error=str(e))
        return False


async def notify_maker_order_activated(
    bot: Bot,
    maker_id: int,
    order_id: str,
    asset: str,
    amount: float,
) -> bool:
    """Notify the Maker that their on-chain deposit was detected and ad is live."""
    branding = get_branding()
    # We might need to add a new template to branding.yaml later,
    # for now we'll use a hardcoded fallback or look it up.
    template = branding.get("notifications", {}).get(
        "order_activated",
        "✅ <b>Ad Activated!</b>\n\nYour deposit for order <code>{order_id_short}</code> "
        "has been detected. Your ad is now live in the P2P Market.\n\n"
        "Asset: <code>{amount:.8g} {asset}</code>",
    )

    text = template.format(
        order_id=order_id,
        order_id_short=order_id[:8],
        asset=asset,
        amount=amount,
    )
    try:
        await bot.send_message(maker_id, text, parse_mode="HTML")
        return True
    except TelegramAPIError as e:
        log.error("notify_maker_order_activated_failed", maker_id=maker_id, error=str(e))
        return False
