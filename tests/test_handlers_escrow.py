"""Tests for escrow handlers."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from bot.handlers import escrow as escrow_handlers
from db.models.order import Order, OrderStatus, OrderType
from db.models.user import User

pytestmark = pytest.mark.unit


async def _create_test_user(session: AsyncSession, telegram_id: int, username: str) -> User:
    async with session.begin():
        user = User(telegram_id=telegram_id, username=username, first_name=username)
        session.add(user)
        return user


async def _create_order(
    session: AsyncSession,
    status: OrderStatus,
    maker_id: int,
    taker_id: int,
) -> Order:
    async with session.begin():
        order = Order(
            id=uuid.uuid4(),
            maker_id=maker_id,
            taker_id=taker_id,
            order_type=OrderType.sell_crypto,
            asset="USDT",
            amount=100.0,
            fiat_currency="USD",
            fiat_amount=100.0,
            payment_method="Sberbank",
            status=status,
            spend_id=str(uuid.uuid4()),
        )
        session.add(order)
        return order


@pytest.mark.asyncio
@patch("bot.handlers.escrow.escrow_service.release_escrow", new_callable=AsyncMock)
async def test_cb_escrow_confirm_success(mock_release: AsyncMock, session: AsyncSession) -> None:
    """Releasing escrow calls the service and shows success."""
    mock_release.return_value = {"status": "completed"}

    callback = AsyncMock()
    callback.from_user.id = 123
    callback.data = "escrow:confirm:5a1fc458-0000-0000-0000-000000000000"
    crypto_pay = AsyncMock()

    await escrow_handlers.cb_escrow_confirm(callback, session, crypto_pay, bot=AsyncMock())

    mock_release.assert_called_once_with(
        session, crypto_pay, order_id="5a1fc458-0000-0000-0000-000000000000", force=False
    )
    callback.message.edit_text.assert_called_once()
    assert "Escrow released" in callback.message.edit_text.call_args[0][0]
    callback.answer.assert_called_once()


@pytest.mark.asyncio
@patch("bot.handlers.escrow.escrow_service.release_escrow", new_callable=AsyncMock)
async def test_cb_escrow_confirm_error(mock_release: AsyncMock, session: AsyncSession) -> None:
    """Escrow release errors are displayed to the user."""
    mock_release.side_effect = ValueError("Order not found")

    callback = AsyncMock()
    callback.from_user.id = 123
    callback.data = "escrow:confirm:5a1fc458-0000-0000-0000-000000000000"
    crypto_pay = AsyncMock()

    await escrow_handlers.cb_escrow_confirm(callback, session, crypto_pay, bot=AsyncMock())

    callback.message.edit_text.assert_called_once()
    assert "Order not found" in callback.message.edit_text.call_args[0][0]
    callback.answer.assert_called_once()


@pytest.mark.asyncio
async def test_cb_order_status_not_found(session: AsyncSession) -> None:
    """Order status handles non-existent orders."""
    callback = AsyncMock()
    callback.data = "order:status:00000000-0000-0000-0000-000000000000"

    await escrow_handlers.cb_order_status(callback, session)

    callback.answer.assert_called_once_with("Order not found.", show_alert=True)


@pytest.mark.asyncio
async def test_cb_order_status_maker_escrow_held(session: AsyncSession) -> None:
    """Maker checking escrow_held order gets confirmation keyboard."""
    await _create_test_user(session, telegram_id=111, username="maker")
    await _create_test_user(session, telegram_id=222, username="taker")
    order = await _create_order(session, status=OrderStatus.escrow_held, maker_id=111, taker_id=222)
    order_id = order.id

    callback = AsyncMock()
    callback.from_user.id = 111  # Maker
    callback.data = f"order:status:{order_id}"

    await escrow_handlers.cb_order_status(callback, session)

    callback.message.answer.assert_called_once()
    assert "Has the taker sent you the fiat payment?" in callback.message.answer.call_args[0][0]
    assert "reply_markup" in callback.message.answer.call_args[1]


@pytest.mark.asyncio
async def test_cb_order_status_taker_escrow_held(session: AsyncSession) -> None:
    """Taker checking escrow_held order gets alert status."""
    await _create_test_user(session, telegram_id=111, username="maker")
    await _create_test_user(session, telegram_id=222, username="taker")
    order = await _create_order(session, status=OrderStatus.escrow_held, maker_id=111, taker_id=222)
    order_id = order.id

    callback = AsyncMock()
    callback.from_user.id = 222  # Taker — not maker, gets alert
    callback.data = f"order:status:{order_id}"

    await escrow_handlers.cb_order_status(callback, session)

    callback.answer.assert_called_once()
    assert "Funds in escrow" in callback.answer.call_args[0][0]
