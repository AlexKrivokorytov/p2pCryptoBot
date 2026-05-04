"""Escrow handlers — Maker confirms fiat receipt and releases funds to Taker."""

from __future__ import annotations

import uuid

import structlog
from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards import (
    active_trade_maker_keyboard,
    back_to_menu_keyboard,
)
from db.models.order import Order
from providers.crypto_pay import CryptoPayClient
from services import escrow_service, notification_service
from utils.formatters import format_error

log = structlog.get_logger(__name__)
router = Router(name="escrow")


@router.callback_query(F.data.startswith("escrow:confirm:"))
async def cb_escrow_confirm(
    callback: CallbackQuery,
    session: AsyncSession,
    crypto_pay: CryptoPayClient,
    bot: Bot,
) -> None:
    """Maker confirms fiat received — release escrow to Taker."""
    order_id = callback.data.split(":")[2]  # type: ignore[union-attr]
    user_id = callback.from_user.id

    try:
        result = await escrow_service.release_escrow(
            session, crypto_pay, order_id=order_id, force=False
        )
        log.info(
            "escrow_confirmed_via_bot",
            user_id=user_id,
            order_id=order_id,
            status=result["status"],
            step="cb_escrow_confirm",
        )
        await callback.message.edit_text(  # type: ignore[union-attr]
            f"✅ <b>Escrow released!</b>\n\n"
            f"Order <code>{order_id[:8]}…</code> is now <b>completed</b>.\n"
            "Crypto has been sent to the taker.",
            reply_markup=back_to_menu_keyboard(),
            parse_mode="HTML",
        )

        # Fetch order details for notification
        order_result = await session.execute(select(Order).where(Order.id == uuid.UUID(order_id)))
        order = order_result.scalar_one_or_none()
        if order and order.taker_id:
            await notification_service.notify_taker_escrow_released(
                bot,
                order.taker_id,
                order_id,
                order.asset,
                float(order.amount) - float(order.total_fee),
            )
    except Exception as exc:
        log.error(
            "escrow_release_failed",
            user_id=user_id,
            order_id=order_id,
            error=str(exc),
            step="cb_escrow_confirm",
        )
        await callback.message.edit_text(  # type: ignore[union-attr]
            format_error(str(exc)),
            reply_markup=back_to_menu_keyboard(),
            parse_mode="HTML",
        )
    await callback.answer()


@router.callback_query(F.data.startswith("order:status:"))
async def cb_order_status(callback: CallbackQuery, session: AsyncSession) -> None:
    """Check current order status."""
    order_id = callback.data.split(":")[2]  # type: ignore[union-attr]
    result = await session.execute(select(Order).where(Order.id == uuid.UUID(order_id)))
    order = result.scalar_one_or_none()
    if order is None:
        await callback.answer("Order not found.", show_alert=True)
        return

    status_map = {
        "pending_funding": "🕐 Awaiting escrow funding",
        "active": "📢 Listed in Order Book — awaiting taker",
        "escrow_held": "🔒 Funds in escrow — awaiting fiat confirmation",
        "completed": "✅ Completed",
        "dispute": "⚠️ Under dispute",
        "cancelled": "❌ Cancelled",
    }
    label = status_map.get(order.status, order.status)

    if order.status == "escrow_held" and order.maker_id == callback.from_user.id:
        await callback.message.answer(  # type: ignore[union-attr]
            f"Order <code>{order_id[:8]}…</code>: {label}\n\n"
            "Has the taker sent you the fiat payment?",
            reply_markup=active_trade_maker_keyboard(order_id),
            parse_mode="HTML",
        )
    else:
        await callback.answer(f"Status: {label}", show_alert=True)
