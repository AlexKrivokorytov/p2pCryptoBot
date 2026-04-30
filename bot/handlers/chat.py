"""Chat handlers for Trade Chat between Maker and Taker."""

from __future__ import annotations

import structlog
from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards import back_to_menu_keyboard
from bot.states import TradeChatFSM
from services import chat_service
from utils.formatters import format_error

log = structlog.get_logger(__name__)
router = Router(name="chat")


@router.callback_query(F.data.startswith("chat:enter:"))
async def cb_chat_enter(callback: CallbackQuery, state: FSMContext) -> None:
    """User clicks 'Chat' to enter the trade chat mode."""
    order_id = callback.data.split(":")[2]  # type: ignore[union-attr]

    await state.update_data(order_id=order_id)
    await state.set_state(TradeChatFSM.chatting)

    await callback.message.edit_text(  # type: ignore[union-attr]
        f"💬 <b>Trade Chat</b>\n\n"
        f"Order: <code>{order_id[:8]}…</code>\n\n"
        "You are now in anonymous chat mode. Any text or photo you send will be "
        "forwarded to the other party.\n\n"
        "<i>To exit chat and return to the menu, tap Exit Chat below or send /cancel.</i>",
        reply_markup=back_to_menu_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(TradeChatFSM.chatting, F.text | F.photo)
async def msg_chat_forward(
    message: Message, state: FSMContext, session: AsyncSession, bot: Bot
) -> None:
    """Forward message to the other participant and save it in the DB."""
    data = await state.get_data()
    order_id = data.get("order_id")

    if not order_id:
        await message.answer("Chat session expired.", reply_markup=back_to_menu_keyboard())
        await state.clear()
        return

    sender_id = message.from_user.id  # type: ignore[union-attr]

    # DB operations inside a single transaction
    async with session.begin():
        # Identify the recipient
        recipient_id = await chat_service.get_other_participant_id(session, order_id, sender_id)

        if not recipient_id:
            await message.answer(
                format_error("Could not find the other participant or order is invalid.")
            )
            return

        text = message.html_text if message.text else message.caption
        photo_file_id = message.photo[-1].file_id if message.photo else None

        # Save to DB
        await chat_service.save_message(
            session=session,
            order_id=order_id,
            sender_id=sender_id,
            message_text=text,
            photo_file_id=photo_file_id,
        )

    # Forward to the other participant
    prefix = "<b>[New Message]</b>\n\n"

    try:
        if photo_file_id:
            await bot.send_photo(
                chat_id=recipient_id,
                photo=photo_file_id,
                caption=prefix + (text or ""),
                parse_mode="HTML",
            )
        else:
            await bot.send_message(
                chat_id=recipient_id,
                text=prefix + text,
                parse_mode="HTML",
            )
    except Exception as e:
        log.error(
            "chat_forward_failed", sender_id=sender_id, recipient_id=recipient_id, error=str(e)
        )
        await message.answer(
            format_error("Failed to deliver message. The other user might have blocked the bot.")
        )
