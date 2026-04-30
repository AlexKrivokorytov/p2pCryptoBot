"""Tests for chat service and handlers."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.handlers import chat as chat_handlers
from bot.states import TradeChatFSM
from db.models.chat import ChatMessage
from db.models.order import Order, OrderStatus, OrderType
from db.models.user import User
from services import chat_service


async def _create_test_order(session: AsyncSession, order_id: str, maker_id: int, taker_id: int) -> Order:
    async with session.begin():
        for uid in (maker_id, taker_id):
            user = await session.get(User, uid)
            if not user:
                user = User(telegram_id=uid, username=f"user_{uid}")
                session.add(user)
                
        order = Order(
            id=uuid.UUID(order_id),
            maker_id=maker_id,
            taker_id=taker_id,
            order_type=OrderType.sell_crypto,
            asset="USDT",
            amount=10.0,
            fiat_currency="USD",
            fiat_amount=100.0,
            payment_method="Bank",
            status=OrderStatus.escrow_held,
            spend_id=order_id,
        )
        session.add(order)
        return order


@pytest.mark.asyncio
async def test_chat_service_save_and_fetch(engine) -> None:
    """Test saving and retrieving messages."""
    factory = async_sessionmaker(engine, expire_on_commit=False)
    order_id = "5a1fc458-0000-0000-0000-000000000000"

    async with factory() as session:
        await _create_test_order(session, order_id, maker_id=111, taker_id=222)
    
    async with factory() as session:
        async with session.begin():
            msg1 = await chat_service.save_message(session, order_id, 111, message_text="Hello taker")
            msg2 = await chat_service.save_message(session, order_id, 222, message_text="Hi maker")

    async with factory() as session:
        history = await chat_service.get_order_chat_history(session, order_id)
        assert len(history) == 2
        assert history[0].message_text == "Hello taker"
        assert history[1].message_text == "Hi maker"


@pytest.mark.asyncio
async def test_get_other_participant_id(engine) -> None:
    """Test resolving the other participant's ID."""
    factory = async_sessionmaker(engine, expire_on_commit=False)
    order_id = "5a1fc458-0000-0000-0000-000000000000"

    async with factory() as session:
        await _create_test_order(session, order_id, maker_id=111, taker_id=222)
    
    async with factory() as session:
        assert await chat_service.get_other_participant_id(session, order_id, 111) == 222
        assert await chat_service.get_other_participant_id(session, order_id, 222) == 111
        assert await chat_service.get_other_participant_id(session, order_id, 999) is None


@pytest.mark.asyncio
async def test_cb_chat_enter() -> None:
    """Test clicking Chat button enters the state."""
    callback = AsyncMock()
    callback.data = "chat:enter:12345"
    state = AsyncMock()
    
    await chat_handlers.cb_chat_enter(callback, state)
    
    state.update_data.assert_called_once_with(order_id="12345")
    state.set_state.assert_called_once_with(TradeChatFSM.chatting)
    callback.message.edit_text.assert_called_once()
    assert "Trade Chat" in callback.message.edit_text.call_args[0][0]


@pytest.mark.asyncio
async def test_msg_chat_forward(engine) -> None:
    """Test forwarding a message in chat."""
    factory = async_sessionmaker(engine, expire_on_commit=False)
    order_id = "5a1fc458-0000-0000-0000-000000000000"

    async with factory() as session:
        await _create_test_order(session, order_id, maker_id=111, taker_id=222)

    message = AsyncMock()
    message.from_user.id = 111
    message.html_text = "I have sent the money"
    message.text = "I have sent the money"
    message.photo = None

    state = AsyncMock()
    state.get_data.return_value = {"order_id": order_id}

    bot = AsyncMock(spec=Bot)

    async with factory() as session:
        await chat_handlers.msg_chat_forward(message, state, session, bot)

    bot.send_message.assert_called_once()
    kwargs = bot.send_message.call_args[1]
    assert kwargs["chat_id"] == 222  # Forwarded to taker
    assert "I have sent the money" in kwargs["text"]
