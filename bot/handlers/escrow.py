"""Escrow handlers — Maker confirms fiat receipt and releases funds to Taker."""

from __future__ import annotations

import structlog
from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards import (
    active_trade_maker_keyboard,
    back_to_menu_keyboard,
)
from providers.crypto_pay import CryptoPayClient
from services import escrow_service, notification_service, order_service
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
        text = (
            f"✅ <b>Escrow released!</b>\n\n"
            f"Order <code>{order_id[:8]}…</code> is now <b>completed</b>.\n"
            "Crypto has been sent to the taker."
        )
        if result.get("on_chain_tx_hash"):
            text += f"\n\n<b>Transaction Hash:</b>\n<code>{result['on_chain_tx_hash']}</code>"

        await callback.message.edit_text(  # type: ignore[union-attr]
            text,
            reply_markup=back_to_menu_keyboard(),
            parse_mode="HTML",
        )

        # Fetch order details via service layer for taker notification
        order = await order_service.get_order_details(session, order_id=order_id)
        if order and order["taker_id"]:
            await notification_service.notify_taker_escrow_released(
                bot,
                order["taker_id"],
                order_id,
                order["asset"],
                order["amount"] - order["total_fee"],
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
    order = await order_service.get_order_details(session, order_id=order_id)

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
    label = status_map.get(order["status"], order["status"])

    msg = f"Order <code>{order_id[:8]}…</code>: {label}\n"

    if order["status"] == "pending_funding" and order.get("escrow_wallet_address"):
        msg += f"\n<b>On-Chain Escrow Address:</b>\n<code>{order['escrow_wallet_address']}</code>\n"
        msg += (
            f"\nPlease send exactly <code>{order['amount']}</code> "
            f"<b>{order['asset']}</b> to this address to activate your ad."
        )
    elif order["status"] == "escrow_held" and order["maker_id"] == callback.from_user.id:
        msg += "\nHas the taker sent you the fiat payment?"
        await callback.message.answer(  # type: ignore[union-attr]
            msg,
            reply_markup=active_trade_maker_keyboard(order_id),
            parse_mode="HTML",
        )
        await callback.answer()
        return

    if order.get("on_chain_tx_hash"):
        msg += f"\n\n<b>TX Hash:</b> <code>{order['on_chain_tx_hash']}</code>"

    await callback.message.answer(msg, reply_markup=back_to_menu_keyboard(), parse_mode="HTML")  # type: ignore[union-attr]
    await callback.answer()
