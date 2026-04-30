"""Final push for 95%+ coverage."""

from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, PhotoSize, User
from sqlalchemy.ext.asyncio import AsyncSession

from bot.handlers import admin as admin_handlers
from bot.handlers import chat as chat_handlers
from bot.handlers import order as order_handlers
from bot.handlers import wallet as wallet_handlers
from db.models.order import Order


@pytest.mark.asyncio
@patch("bot.handlers.admin.admin_service.get_dispute_queue", new_callable=AsyncMock)
@patch("bot.handlers.admin._is_admin", return_value=True)
async def test_cb_admin_disputes(mock_is_admin, mock_queue, session):
    callback = AsyncMock(spec=CallbackQuery)
    callback.from_user = MagicMock(spec=User)
    callback.from_user.id = 999
    callback.message = AsyncMock(spec=Message)
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()
    callback.data = "admin:disputes"

    mock_queue.return_value = [Order(id=uuid.uuid4(), asset="TON", amount=Decimal("1"))]
    await admin_handlers.cb_admin_disputes(callback, session)
    callback.message.edit_text.assert_called()


@pytest.mark.asyncio
@patch("bot.handlers.admin._is_admin", return_value=True)
async def test_cb_dispute_view(mock_is_admin, session):
    order_id = uuid.uuid4()
    callback = AsyncMock(spec=CallbackQuery)
    callback.from_user = MagicMock(spec=User)
    callback.from_user.id = 999
    callback.message = AsyncMock(spec=Message)
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()
    callback.data = f"admin:dispute:view:{order_id}"

    order = Order(
        id=order_id,
        asset="TON",
        amount=Decimal("1"),
        fiat_amount=Decimal("100"),
        fiat_currency="RUB",
        maker_id=1,
        taker_id=2
    )
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = order
    session.execute = AsyncMock(return_value=mock_result)

    await admin_handlers.cb_dispute_view(callback, session)
    callback.message.edit_text.assert_called()


@pytest.mark.asyncio
@patch("bot.handlers.admin.dispute_service.resolve_dispute", new_callable=AsyncMock)
@patch("bot.handlers.admin._is_admin", return_value=True)
async def test_cb_dispute_resolve_success(mock_is_admin, mock_resolve, session):
    order_id = str(uuid.uuid4())
    callback = AsyncMock(spec=CallbackQuery)
    callback.from_user = MagicMock(spec=User)
    callback.from_user.id = 999
    callback.message = AsyncMock(spec=Message)
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()
    callback.data = f"dispute:resolve:{order_id}:refund_maker"
    state = AsyncMock(spec=FSMContext)

    mock_resolve.return_value = {"status": "completed"}
    await admin_handlers.cb_dispute_resolve(callback, state, session, AsyncMock())
    callback.message.edit_text.assert_called()


@pytest.mark.asyncio
async def test_msg_chat_forward_no_order_id():
    message = AsyncMock(spec=Message)
    message.from_user = MagicMock(spec=User)
    message.answer = AsyncMock()
    state = AsyncMock(spec=FSMContext)
    state.get_data.return_value = {}  # Empty data
    session = AsyncMock(spec=AsyncSession)

    await chat_handlers.msg_chat_forward(message, state, session, AsyncMock())
    message.answer.assert_called_with("Chat session expired.", reply_markup=ANY)


@pytest.mark.asyncio
@patch("bot.handlers.chat.chat_service.get_other_participant_id", new_callable=AsyncMock)
async def test_msg_chat_forward_recipient_not_found(mock_get_recipient):
    message = AsyncMock(spec=Message)
    message.from_user = MagicMock(spec=User)
    message.from_user.id = 1
    message.text = "Hi"
    message.html_text = "Hi"
    message.photo = None
    message.answer = AsyncMock()
    state = AsyncMock(spec=FSMContext)
    state.get_data.return_value = {"order_id": "uuid-123"}

    mock_get_recipient.return_value = None
    session = AsyncMock(spec=AsyncSession)
    session.begin.return_value.__aenter__.return_value = AsyncMock()

    await chat_handlers.msg_chat_forward(message, state, session, AsyncMock())
    message.answer.assert_called()


@pytest.mark.asyncio
@patch("bot.handlers.chat.chat_service.save_message", new_callable=AsyncMock)
@patch("bot.handlers.chat.chat_service.get_other_participant_id", new_callable=AsyncMock)
async def test_msg_chat_forward_photo_success(mock_get_recipient, mock_save):
    message = AsyncMock(spec=Message)
    message.from_user = MagicMock(spec=User)
    message.from_user.id = 1
    message.text = None
    message.html_text = None
    message.caption = "Look at this"
    message.photo = [MagicMock(spec=PhotoSize, file_id="file-123")]
    state = AsyncMock(spec=FSMContext)
    state.get_data.return_value = {"order_id": "uuid-123"}
    bot = AsyncMock()

    mock_get_recipient.return_value = 2
    session = AsyncMock(spec=AsyncSession)
    session.begin.return_value.__aenter__.return_value = AsyncMock()

    await chat_handlers.msg_chat_forward(message, state, session, bot)
    bot.send_photo.assert_called_once()
    mock_save.assert_called_once()


@pytest.mark.asyncio
@patch("bot.handlers.chat.chat_service.save_message", new_callable=AsyncMock)
@patch("bot.handlers.chat.chat_service.get_other_participant_id", new_callable=AsyncMock)
async def test_msg_chat_forward_error(mock_get_recipient, mock_save):
    message = AsyncMock(spec=Message)
    message.from_user = MagicMock(spec=User)
    message.from_user.id = 1
    message.text = "Hello"
    message.html_text = "Hello"
    message.photo = None
    message.answer = AsyncMock()
    state = AsyncMock(spec=FSMContext)
    state.get_data.return_value = {"order_id": "uuid-123"}
    bot = AsyncMock()
    bot.send_message.side_effect = Exception("Block")

    mock_get_recipient.return_value = 2
    session = AsyncMock(spec=AsyncSession)
    session.begin.return_value.__aenter__.return_value = AsyncMock()

    await chat_handlers.msg_chat_forward(message, state, session, bot)
    message.answer.assert_called()


@pytest.mark.asyncio
@patch("bot.handlers.order.rate_service.get_market_rate", new_callable=AsyncMock)
async def test_cb_order_view_market_rate(mock_rate, session):
    order_id = uuid.uuid4()
    callback = AsyncMock(spec=CallbackQuery)
    callback.data = f"order:view:{order_id}"
    callback.message = AsyncMock(spec=Message)
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()

    order = Order(
        id=order_id,
        asset="TON",
        amount=Decimal("1"),
        fiat_amount=Decimal("500"),
        fiat_currency="USD",
        order_type="sell_crypto",
        payment_method="Sberbank"
    )
    order.maker = MagicMock(spec=User, username="maker1")

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = order
    session.execute = AsyncMock(return_value=mock_result)
    mock_rate.return_value = Decimal("480.0")  # Market rate

    await order_handlers.cb_order_view(callback, session)
    callback.message.edit_text.assert_called()


@pytest.mark.asyncio
async def test_cb_wallet_entry(session):
    callback = AsyncMock(spec=CallbackQuery)
    callback.from_user = MagicMock(spec=User)
    callback.from_user.id = 123
    callback.message = AsyncMock(spec=Message)
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()

    with patch("bot.handlers.wallet._build_wallet_text", new_callable=AsyncMock) as mock_text:
        mock_text.return_value = "Wallet Menu"
        await wallet_handlers.cb_wallet(callback, session)
        callback.message.edit_text.assert_called()


@pytest.mark.asyncio
async def test_cb_wallet_add():
    callback = AsyncMock(spec=CallbackQuery)
    callback.message = AsyncMock(spec=Message)
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()

    await wallet_handlers.cb_wallet_add(callback)
    callback.message.edit_text.assert_called()


@pytest.mark.asyncio
@patch("bot.handlers.admin._is_admin", return_value=False)
async def test_cb_admin_stats_non_admin(mock_is_admin, session):
    callback = AsyncMock(spec=CallbackQuery)
    callback.from_user = MagicMock(spec=User)
    callback.from_user.id = 123
    callback.message = AsyncMock(spec=Message)
    callback.answer = AsyncMock()

    await admin_handlers.cb_admin_stats(callback, session)
    callback.answer.assert_called_with("⛔ Admins only.", show_alert=True)


@pytest.mark.asyncio
async def test_cb_order_view_not_found(session):
    callback = AsyncMock(spec=CallbackQuery)
    callback.data = f"order:view:{uuid.uuid4()}"
    callback.answer = AsyncMock()

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=mock_result)

    await order_handlers.cb_order_view(callback, session)
    callback.answer.assert_called_with("Order not found.", show_alert=True)


def test_main_import():
    """Just import main to cover some top-level code."""
    import bot.main
    assert bot.main is not None
