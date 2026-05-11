"""Dispute handlers — raise and confirm dispute flow."""

from __future__ import annotations

import structlog
from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards import back_to_menu_keyboard
from bot.states import DisputeFSM
from services import dispute_service, notification_service, order_service
from utils.formatters import format_dispute_raised, format_error

log = structlog.get_logger(__name__)
router = Router(name="dispute")


@router.callback_query(F.data.startswith("dispute:raise:"))
async def cb_dispute_raise(callback: CallbackQuery, state: FSMContext) -> None:
    """Start dispute flow — prompt for reason."""
    order_id = callback.data.split(":")[2]  # type: ignore[union-attr]
    await state.set_state(DisputeFSM.enter_reason)
    await state.update_data(order_id=order_id)
    await callback.message.answer(  # type: ignore[union-attr]
        "⚠️ <b>Raise a Dispute</b>\n\nPlease describe the issue briefly:",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(DisputeFSM.enter_reason)
async def msg_dispute_reason(message: Message, state: FSMContext) -> None:
    """Store reason, show confirm prompt."""
    reason = (message.text or "").strip()
    if not reason:
        await message.answer(format_error("Reason cannot be empty."), parse_mode="HTML")
        return

    await state.update_data(reason=reason)
    await state.set_state(DisputeFSM.confirm_dispute)
    await message.answer(
        f"📋 <b>Dispute reason:</b>\n{reason}\n\nConfirm to raise dispute?",
        reply_markup=_dispute_confirm_inline(),
        parse_mode="HTML",
    )


def _dispute_confirm_inline() -> InlineKeyboardMarkup:
    from aiogram.types import InlineKeyboardButton
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Confirm", callback_data="dispute:confirmed"),
        InlineKeyboardButton(text="❌ Cancel", callback_data="dispute:abort"),
    )
    return builder.as_markup()


@router.callback_query(DisputeFSM.confirm_dispute, F.data == "dispute:confirmed")
async def cb_dispute_confirmed(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
) -> None:
    """Submit the dispute to DB."""
    data = await state.get_data()
    await state.clear()
    user_id = callback.from_user.id
    order_id: str = data["order_id"]
    reason: str = data["reason"]

    try:
        await dispute_service.raise_dispute(
            session, order_id=order_id, reason=reason, raised_by=user_id
        )
        await callback.message.edit_text(  # type: ignore[union-attr]
            format_dispute_raised(order_id, reason),
            reply_markup=back_to_menu_keyboard(),
            parse_mode="HTML",
        )

        # Notify both parties
        order = await order_service.get_order_details(session, order_id=order_id)
        if order:
            await notification_service.notify_dispute_opened(
                bot, order["maker_id"], order["taker_id"], order_id, reason
            )
        log.info(
            "dispute_submitted",
            user_id=user_id,
            order_id=order_id,
            step="cb_dispute_confirmed",
            status="ok",
        )
    except Exception as exc:
        await callback.message.edit_text(  # type: ignore[union-attr]
            format_error(str(exc)),
            reply_markup=back_to_menu_keyboard(),
            parse_mode="HTML",
        )
    await callback.answer()


@router.callback_query(F.data == "dispute:abort")
async def cb_dispute_abort(callback: CallbackQuery, state: FSMContext) -> None:
    """Abort dispute flow."""
    await state.clear()
    await callback.message.edit_text(  # type: ignore[union-attr]
        "Dispute cancelled.",
        reply_markup=back_to_menu_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()
