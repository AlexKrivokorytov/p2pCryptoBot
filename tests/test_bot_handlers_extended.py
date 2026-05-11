"""Extended tests for bot handlers to reach 98% coverage."""

from decimal import Decimal
from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest
from aiogram.types import CallbackQuery, Message, SuccessfulPayment
from aiogram.types import User as TgUser

from bot.handlers.admin import (
    cb_admin_disputes,
    cb_dispute_view,
)
from bot.handlers.b2b import cb_b2b_buy, cb_b2b_pay_ton, cb_b2b_spawn, msg_successful_payment
from bot.handlers.chat import cb_chat_enter, msg_chat_forward
from bot.handlers.order import cb_order_view
from services.bot_spawner import BotSpawnerService


@pytest.fixture
def admin_user():
    return TgUser(id=123, is_bot=False, first_name="Admin", username="admin")


@pytest.fixture
def regular_user():
    return TgUser(id=456, is_bot=False, first_name="User", username="user")


@pytest.mark.asyncio
async def test_cb_b2b_buy():
    callback = AsyncMock(spec=CallbackQuery)
    callback.message = AsyncMock(spec=Message)
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()
    await cb_b2b_buy(callback)
    callback.message.edit_text.assert_called_once()


@pytest.mark.asyncio
async def test_cb_b2b_pay_ton(session):
    callback = AsyncMock(spec=CallbackQuery)
    callback.from_user = TgUser(id=123, is_bot=False, first_name="Test")
    callback.message = AsyncMock(spec=Message)
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()
    with (
        patch("services.b2b_service.get_ton_license_price", return_value=1.0),
        patch("services.b2b_service.create_ton_invoice", return_value={"memo": "test"}),
    ):
        await cb_b2b_pay_ton(callback, session)
        callback.message.edit_text.assert_called_once()


@pytest.mark.asyncio
async def test_cb_b2b_spawn(session):
    callback = AsyncMock(spec=CallbackQuery)
    callback.from_user = TgUser(id=123, is_bot=False, first_name="Test")
    callback.message = AsyncMock(spec=Message)
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()
    with (
        patch("services.b2b_service.get_active_license", return_value={"license_id": "lic_123"}),
        patch("bot.handlers.b2b.settings.MASTER_BOT_USERNAME", "p2p_master_bot"),
    ):
        await cb_b2b_spawn(callback, session)
        callback.message.edit_text.assert_called_once()
        callback.answer.assert_called_once()


@pytest.mark.asyncio
async def test_handle_managed_bot_created_success(session):
    message = AsyncMock(spec=Message)
    message.from_user = TgUser(id=123, is_bot=False, first_name="Test")
    message.managed_bot_created = MagicMock()
    message.managed_bot_created.bot_id = 999
    message.managed_bot_created.bot_username = "new_bot"
    message.bot = AsyncMock()
    message.bot.get_managed_bot_token = AsyncMock(return_value=MagicMock(token="123:ABC"))
    message.answer = AsyncMock()

    bot_spawner = AsyncMock(spec=BotSpawnerService)
    bot_spawner.update_bot_token = AsyncMock()

    from bot.handlers.b2b import handle_managed_bot_created

    with patch("services.b2b_service.get_active_license", return_value={"license_id": "lic_123"}):
        await handle_managed_bot_created(message, session, bot_spawner)
        bot_spawner.update_bot_token.assert_called_once_with(ANY, "lic_123", "123:ABC")
        message.answer.assert_called()


@pytest.mark.asyncio
async def test_msg_successful_payment(session):
    message = AsyncMock(spec=Message)
    message.from_user = TgUser(id=123, is_bot=False, first_name="Test")
    message.successful_payment = MagicMock(spec=SuccessfulPayment)
    message.successful_payment.telegram_payment_charge_id = "charge_123"
    message.answer = AsyncMock()
    with patch(
        "services.b2b_service.create_b2b_license",
        return_value={"license_id": "lic_123", "expires_at": MagicMock()},
    ):
        await msg_successful_payment(message, session)
        message.answer.assert_called()


@pytest.mark.asyncio
async def test_cb_order_view_success(session):
    callback = AsyncMock(spec=CallbackQuery)
    callback.data = "order:view:123"
    callback.message = AsyncMock(spec=Message)
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()
    order_data = {
        "order_type": "sell_crypto",
        "maker_username": "maker",
        "amount": 1.0,
        "fiat_amount": 100.0,
        "asset": "USDT",
        "fiat_currency": "USD",
        "payment_method": "Any",
    }
    with (
        patch("services.order_service.get_order_details", return_value=order_data),
        patch("services.rate_service.get_market_rate", return_value=Decimal("100.0")),
    ):
        await cb_order_view(callback, session)
        callback.message.edit_text.assert_called_once()


@pytest.mark.asyncio
async def test_cb_admin_disputes_authorized(admin_user, session):
    callback = AsyncMock(spec=CallbackQuery)
    callback.from_user = admin_user
    callback.message = AsyncMock(spec=Message)
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()
    with (
        patch("bot.handlers.admin.settings.ADMIN_IDS", [123]),
        patch("services.admin_service.get_dispute_queue", return_value=[]),
    ):
        await cb_admin_disputes(callback, session)
        callback.message.edit_text.assert_called_once()


@pytest.mark.asyncio
async def test_cb_dispute_view_success(admin_user, session):
    callback = AsyncMock(spec=CallbackQuery)
    callback.from_user = admin_user
    callback.data = "admin:dispute:view:123"
    callback.message = AsyncMock(spec=Message)
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()
    order_data = {
        "asset": "USDT",
        "amount": 1.0,
        "fiat_amount": 100.0,
        "fiat_currency": "USD",
        "maker_username": "maker",
        "taker_username": "taker",
        "dispute_reason": "test",
    }
    with (
        patch("bot.handlers.admin.settings.ADMIN_IDS", [123]),
        patch("services.order_service.get_order_details", return_value=order_data),
    ):
        await cb_dispute_view(callback, session)
        callback.message.edit_text.assert_called_once()


@pytest.mark.asyncio
async def test_cb_chat_enter():
    callback = AsyncMock(spec=CallbackQuery)
    callback.data = "chat:enter:123"
    callback.message = AsyncMock(spec=Message)
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()
    state = AsyncMock()
    state.update_data = AsyncMock()
    state.set_state = AsyncMock()
    await cb_chat_enter(callback, state)
    state.set_state.assert_called()
    callback.message.edit_text.assert_called_once()


@pytest.mark.asyncio
async def test_msg_chat_forward_success(session):
    message = AsyncMock(spec=Message)
    message.from_user = TgUser(id=123, is_bot=False, first_name="Test")
    message.text = "Hello"
    message.html_text = "Hello"
    message.photo = None  # Ensure photo attribute exists
    message.answer = AsyncMock()
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={"order_id": "123"})
    bot = AsyncMock()
    bot.send_message = AsyncMock()
    with (
        patch("services.chat_service.get_other_participant_id", return_value=456),
        patch("services.chat_service.save_message", return_value=None),
    ):
        await msg_chat_forward(message, state, session, bot)
        bot.send_message.assert_called_once()
