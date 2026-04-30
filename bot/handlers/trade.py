"""Trade handlers — Taker accepts order + active trade management."""

from __future__ import annotations

import structlog
from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards import (
    active_trade_taker_keyboard,
    back_to_menu_keyboard,
)
from db.models.order import Order
from services import notification_service, order_service
from utils.formatters import format_error

log = structlog.get_logger(__name__)
router = Router(name="trade")


# ── Take order ─────────────────────────────────────────────────────────────────


@router.callback_query(F.data.startswith("trade:take:"))
async def cb_take_order(
    callback: CallbackQuery,
    session: AsyncSession,
    bot: Bot,
) -> None:
    """Taker accepts an active order from the Order Book.

    Calls ``order_service.take_order()`` which uses ``with_for_update()``
    to prevent race conditions when two users try to accept simultaneously.
    """
    order_id = callback.data.split(":")[2]  # type: ignore[union-attr]
    taker_id = callback.from_user.id

    try:
        result = await order_service.take_order(session, order_id=order_id, taker_id=taker_id)
    except ValueError as exc:
        await callback.message.edit_text(  # type: ignore[union-attr]
            format_error(str(exc)),
            reply_markup=back_to_menu_keyboard(),
            parse_mode="HTML",
        )
        await callback.answer()
        return

    log.info(
        "trade_accepted",
        taker_id=taker_id,
        order_id=order_id,
        maker_id=result["maker_id"],
        step="cb_take_order",
    )

    await callback.message.edit_text(  # type: ignore[union-attr]
        f"🤝 <b>Trade accepted!</b>\n\n"
        f"Order: <code>{order_id[:8]}…</code>\n\n"
        "The funds are locked in escrow. Please complete the fiat transfer.\n"
        "Once done, tap <b>I've sent fiat</b>.",
        reply_markup=active_trade_taker_keyboard(order_id),
        parse_mode="HTML",
    )
    await callback.answer()

    taker_username = callback.from_user.username
    await notification_service.notify_maker_taker_found(
        bot, result["maker_id"], taker_username, order_id
    )


# ── Taker: fiat sent notification ──────────────────────────────────────────────


@router.callback_query(F.data.startswith("trade:fiat_sent:"))
async def cb_fiat_sent(callback: CallbackQuery, session: AsyncSession, bot: Bot) -> None:
    """Taker notifies that fiat has been sent to the Maker."""
    order_id = callback.data.split(":")[2]  # type: ignore[union-attr]

    await callback.message.edit_text(  # type: ignore[union-attr]
        f"💸 <b>Fiat sent!</b>\n\n"
        f"Order: <code>{order_id[:8]}…</code>\n\n"
        "Waiting for the seller to confirm receipt.\n"
        "You will be notified when crypto is released.",
        reply_markup=back_to_menu_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()

    # Send push notification to Maker
    async with session.begin():
        order = await session.get(Order, order_id)
        if order and order.maker_id:
            await notification_service.notify_maker_fiat_sent(bot, order.maker_id, order_id)
