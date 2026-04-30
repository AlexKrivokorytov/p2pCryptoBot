"""Tests for trade handlers."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from bot.handlers import trade as trade_handlers
from db.models.order import Order, OrderStatus, OrderType
from db.models.user import User


async def _create_test_order(session: AsyncSession, order_id: str, maker_id: int) -> Order:
    async with session.begin():
        user = await session.get(User, maker_id)
        if not user:
            user = User(telegram_id=maker_id, username=f"user_{maker_id}", first_name="T")
            session.add(user)

        order = Order(
            id=uuid.UUID(order_id),
            maker_id=maker_id,
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
@patch("bot.handlers.trade.order_service.take_order", new_callable=AsyncMock)
@patch("bot.handlers.trade.notification_service.notify_maker_taker_found", new_callable=AsyncMock)
async def test_cb_take_order_success(
    mock_notify: AsyncMock,
    mock_take: AsyncMock,
    session: AsyncSession,
) -> None:
    """Taker successfully accepts an order and maker is notified."""
    mock_take.return_value = {"maker_id": 999, "status": "escrow_held"}

    callback = AsyncMock()
    callback.from_user.id = 123
    callback.from_user.username = "taker_usr"
    callback.data = "trade:take:5a1fc458"
    bot = AsyncMock(spec=Bot)

    await trade_handlers.cb_take_order(callback, session, bot)

    mock_take.assert_called_once_with(session, order_id="5a1fc458", taker_id=123)
    mock_notify.assert_called_once_with(bot, 999, "taker_usr", "5a1fc458")
    callback.message.edit_text.assert_called_once()
    assert "Trade accepted!" in callback.message.edit_text.call_args[0][0]
    callback.answer.assert_called_once()


@pytest.mark.asyncio
@patch("bot.handlers.trade.order_service.take_order", new_callable=AsyncMock)
async def test_cb_take_order_error(mock_take: AsyncMock, session: AsyncSession) -> None:
    """Order taken by someone else or not found shows error."""
    mock_take.side_effect = ValueError("Order is no longer available")

    callback = AsyncMock()
    callback.from_user.id = 123
    callback.data = "trade:take:5a1fc458"
    bot = AsyncMock(spec=Bot)

    await trade_handlers.cb_take_order(callback, session, bot)

    callback.message.edit_text.assert_called_once()
    assert "Order is no longer available" in callback.message.edit_text.call_args[0][0]
    callback.answer.assert_called_once()


@pytest.mark.asyncio
@patch("bot.handlers.trade.notification_service.notify_maker_fiat_sent", new_callable=AsyncMock)
async def test_cb_fiat_sent(mock_notify: AsyncMock, session: AsyncSession) -> None:
    """Taker notifies fiat sent and maker is notified."""
    # First create an order in DB so cb_fiat_sent finds the maker_id
    order_id = "5a1fc458-0000-0000-0000-000000000000"
    await _create_test_order(session, order_id, maker_id=999)

    callback = AsyncMock()
    callback.data = f"trade:fiat_sent:{order_id}"
    bot = AsyncMock(spec=Bot)

    await trade_handlers.cb_fiat_sent(callback, session, bot)

    mock_notify.assert_called_once_with(bot, 999, order_id)
    callback.message.edit_text.assert_called_once()
    assert "Fiat sent!" in callback.message.edit_text.call_args[0][0]
    callback.answer.assert_called_once()
