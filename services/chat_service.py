"""Chat service for Trade Chat."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.chat import ChatMessage
from db.models.order import Order


async def save_message(
    session: AsyncSession,
    order_id: str | uuid.UUID,
    sender_id: int,
    message_text: str | None = None,
    photo_file_id: str | None = None,
) -> ChatMessage:
    """Save a chat message to the database."""
    if isinstance(order_id, str):
        order_id = uuid.UUID(order_id)

    chat_msg = ChatMessage(
        order_id=order_id,
        sender_id=sender_id,
        message_text=message_text,
        photo_file_id=photo_file_id,
    )
    session.add(chat_msg)
    await session.flush()
    return chat_msg


async def get_order_chat_history(
    session: AsyncSession, order_id: str | uuid.UUID
) -> list[ChatMessage]:
    """Retrieve chat history for a specific order."""
    if isinstance(order_id, str):
        order_id = uuid.UUID(order_id)

    result = await session.execute(
        select(ChatMessage)
        .where(ChatMessage.order_id == order_id)
        .order_by(ChatMessage.created_at.asc())
    )
    return list(result.scalars().all())


async def get_other_participant_id(
    session: AsyncSession, order_id: str | uuid.UUID, sender_id: int
) -> int | None:
    """Return the telegram ID of the other participant in the trade."""
    if isinstance(order_id, str):
        order_id = uuid.UUID(order_id)

    order = await session.get(Order, order_id)
    if not order:
        return None

    if order.maker_id == sender_id:
        return order.taker_id
    elif order.taker_id == sender_id:
        return order.maker_id

    return None
