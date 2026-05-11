"""Admin handlers — moderator-only commands for dispute arbitration and platform stats.

Access control: all handlers check ADMIN_IDS from Settings.
Commands:
  /admin   — open the admin dashboard
  /disputes — shortcut to the dispute queue
  /stats   — shortcut to platform stats
  /arbitrate <order_id> — enter arbitration FSM for a specific order
"""

from __future__ import annotations

import structlog
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.keyboards import (
    admin_dashboard_keyboard,
    admin_dispute_action_keyboard,
    admin_disputes_keyboard,
    dispute_resolve_keyboard,
)
from bot.states import ArbitrationFSM
from providers.crypto_pay import CryptoPayClient
from services import admin_service, dispute_service, order_service
from utils.formatters import format_error

log = structlog.get_logger(__name__)
router = Router(name="admin")


def _is_admin(user_id: int) -> bool:
    """Return True if *user_id* is in the configured ADMIN_IDS list."""
    return user_id in settings.ADMIN_IDS


# ── /admin  ────────────────────────────────────────────────────────────────────


@router.message(Command("admin"))
async def cmd_admin(message: Message) -> None:
    """Open the admin dashboard for authorised moderators."""
    if not message.from_user or not _is_admin(message.from_user.id):
        await message.answer("⛔ Admins only.")
        return

    await message.answer(
        "🛡️ <b>Admin Dashboard</b>\n\nChoose an action:",
        reply_markup=admin_dashboard_keyboard(),
        parse_mode="HTML",
    )


# ── /stats ─────────────────────────────────────────────────────────────────────


@router.message(Command("stats"))
async def cmd_stats(message: Message, session: AsyncSession) -> None:
    """Show platform stats (admin only)."""
    if not message.from_user or not _is_admin(message.from_user.id):
        await message.answer("⛔ Admins only.")
        return

    stats = await admin_service.get_platform_stats(session)
    await message.answer(
        admin_service.format_stats_message(stats),
        reply_markup=admin_dashboard_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(F.data.in_({"admin:stats", "admin:stats:refresh"}))
async def cb_admin_stats(callback: CallbackQuery, session: AsyncSession) -> None:
    """Inline: show / refresh platform stats."""
    if (
        not callback.from_user
        or not isinstance(callback.message, Message)
        or not _is_admin(callback.from_user.id)
    ):
        await callback.answer("⛔ Admins only.", show_alert=True)
        return

    stats = await admin_service.get_platform_stats(session)
    await callback.message.edit_text(
        admin_service.format_stats_message(stats),
        reply_markup=admin_dashboard_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer(
        "✅ Stats refreshed" if callback.data and "refresh" in callback.data else ""
    )


# ── /disputes ──────────────────────────────────────────────────────────────────


@router.message(Command("disputes"))
async def cmd_disputes(message: Message, session: AsyncSession) -> None:
    """Show the dispute queue (admin only)."""
    if not message.from_user or not _is_admin(message.from_user.id):
        await message.answer("⛔ Admins only.")
        return

    orders = await admin_service.get_dispute_queue(session)
    count = len(orders)
    header = (
        f"⚖️ <b>Dispute Queue</b> — {count} open dispute{'s' if count != 1 else ''}\n\n"
        if count
        else "⚖️ <b>Dispute Queue</b>\n\n✅ No open disputes right now."
    )
    lines = [admin_service.format_dispute_order(o, i) for i, o in enumerate(orders, start=1)]
    text = header + "\n".join(lines)
    await message.answer(
        text,
        reply_markup=admin_disputes_keyboard(orders),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "admin:disputes")
async def cb_admin_disputes(callback: CallbackQuery, session: AsyncSession) -> None:
    """Inline: show the dispute queue."""
    if (
        not callback.from_user
        or not isinstance(callback.message, Message)
        or not _is_admin(callback.from_user.id)
    ):
        await callback.answer("⛔ Admins only.", show_alert=True)
        return

    orders = await admin_service.get_dispute_queue(session)
    count = len(orders)
    header = (
        f"⚖️ <b>Dispute Queue</b> — {count} open dispute{'s' if count != 1 else ''}\n\n"
        if count
        else "⚖️ <b>Dispute Queue</b>\n\n✅ No open disputes right now."
    )
    lines = [admin_service.format_dispute_order(o, i) for i, o in enumerate(orders, start=1)]
    text = header + "\n".join(lines)
    await callback.message.edit_text(
        text,
        reply_markup=admin_disputes_keyboard(orders),
        parse_mode="HTML",
    )
    await callback.answer()


# ── Dispute detail view ────────────────────────────────────────────────────────


@router.callback_query(F.data.startswith("admin:dispute:view:"))
async def cb_dispute_view(callback: CallbackQuery, session: AsyncSession) -> None:
    """Show full detail of a single disputed order with resolve actions."""
    if (
        not callback.from_user
        or not isinstance(callback.message, Message)
        or not _is_admin(callback.from_user.id)
    ):
        await callback.answer("⛔ Admins only.", show_alert=True)
        return

    order_id_str = callback.data.split(":")[-1]  # type: ignore[union-attr]
    order = await order_service.get_order_details(session, order_id=order_id_str)

    if order is None:
        await callback.answer("Order not found.", show_alert=True)
        return

    maker_name = order["maker_username"]
    taker_name = order["taker_username"] or "—"

    text = (
        f"⚖️ <b>Dispute Detail</b>\n\n"
        f"Order: <code>{order_id_str[:8]}…</code>\n"
        f"Asset: <b>{order['asset']}</b>  "
        f"Amount: <code>{order['amount']:.6g}</code>\n"
        f"Fiat: <code>{order['fiat_amount']:.2f} {order['fiat_currency']}</code>\n"
        f"Maker: @{maker_name}  Taker: @{taker_name}\n"
        f"Reason: <i>{order['dispute_reason'] or 'Not specified'}</i>\n\n"
        "Choose resolution:"
    )

    await callback.message.edit_text(
        text,
        reply_markup=admin_dispute_action_keyboard(order_id_str),
        parse_mode="HTML",
    )
    await callback.answer()


# ── Dispute resolution callback ────────────────────────────────────────────────


@router.callback_query(F.data.startswith("dispute:resolve:"))
async def cb_dispute_resolve(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    crypto_pay: CryptoPayClient,
) -> None:
    """Execute moderator dispute resolution decision."""
    parts = callback.data.split(":")  # type: ignore[union-attr]
    # format: dispute:resolve:<order_id>:<decision>
    order_id = parts[2]
    decision = parts[3]
    if not callback.from_user or not isinstance(callback.message, Message):
        return
    moderator_id = callback.from_user.id

    if not _is_admin(moderator_id):
        await callback.answer("⛔ Admins only.", show_alert=True)
        return

    await state.clear()
    try:
        result = await dispute_service.resolve_dispute(
            session,
            crypto_pay,
            order_id=order_id,
            decision=decision,
            moderator_id=moderator_id,
        )
        await callback.message.edit_text(
            f"✅ <b>Dispute resolved</b>\n\n"
            f"Order: <code>{order_id[:8]}…</code>\n"
            f"Decision: <b>{decision}</b>\n"
            f"Status: <b>{result['status']}</b>",
            reply_markup=admin_dashboard_keyboard(),
            parse_mode="HTML",
        )
        log.info(
            "dispute_resolved_via_admin",
            order_id=order_id,
            moderator_id=moderator_id,
            decision=decision,
            status=result["status"],
            step="cb_dispute_resolve",
        )
    except Exception as exc:
        await callback.message.edit_text(
            format_error(str(exc)),
            reply_markup=admin_dashboard_keyboard(),
            parse_mode="HTML",
        )
    await callback.answer()


# ── /arbitrate (FSM flow) ──────────────────────────────────────────────────────


@router.message(Command("arbitrate"))
async def cmd_arbitrate(message: Message, state: FSMContext) -> None:
    """Admin: start arbitration FSM for a disputed order by ID."""
    if not message.from_user or not _is_admin(message.from_user.id):
        await message.answer("⛔ Admins only.")
        return
    await state.set_state(ArbitrationFSM.enter_order_id)
    await message.answer("🔍 Enter the <b>Order ID</b> to arbitrate:", parse_mode="HTML")


@router.message(ArbitrationFSM.enter_order_id)
async def msg_arb_order_id(message: Message, state: FSMContext) -> None:
    """Store order ID, show decision keyboard."""
    order_id = (message.text or "").strip()
    if len(order_id) < 8:
        await message.answer(format_error("Invalid order ID."), parse_mode="HTML")
        return
    await state.update_data(order_id=order_id)
    await state.set_state(ArbitrationFSM.choose_decision)
    await message.answer(
        f"⚖️ Dispute resolution for order <code>{order_id[:8]}…</code>\n\nChoose decision:",
        reply_markup=dispute_resolve_keyboard(order_id),
        parse_mode="HTML",
    )
