"""B2B Phase 3 tests — Telegram Stars payments."""

import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.types import CallbackQuery, Message, PreCheckoutQuery, SuccessfulPayment, User
from sqlalchemy.ext.asyncio import AsyncSession

from bot.handlers import b2b as b2b_handlers

pytestmark = pytest.mark.b2b


@pytest.mark.asyncio
async def test_cb_b2b_menu_no_license(session: AsyncSession):
    callback = AsyncMock(spec=CallbackQuery)
    callback.from_user = MagicMock(spec=User)
    callback.from_user.id = 12345
    callback.message = AsyncMock(spec=Message)
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()

    with patch(
        "bot.handlers.b2b.b2b_service.get_active_license", new_callable=AsyncMock
    ) as mock_get:
        mock_get.return_value = None
        await b2b_handlers.cb_b2b_menu(callback, session)

        callback.message.edit_text.assert_called()
        args, kwargs = callback.message.edit_text.call_args
        assert "No active license" in args[0]


@pytest.mark.asyncio
async def test_cb_b2b_menu_with_license(session: AsyncSession):
    callback = AsyncMock(spec=CallbackQuery)
    callback.from_user = MagicMock(spec=User)
    callback.from_user.id = 12345
    callback.message = AsyncMock(spec=Message)
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()

    with patch(
        "bot.handlers.b2b.b2b_service.get_active_license", new_callable=AsyncMock
    ) as mock_get:
        mock_get.return_value = {
            "license_id": str(uuid.uuid4()),
            "expires_at": datetime(2030, 1, 1),
            "is_active": True,
        }
        await b2b_handlers.cb_b2b_menu(callback, session)

        callback.message.edit_text.assert_called()
        args, kwargs = callback.message.edit_text.call_args
        assert "Active License" in args[0]


@pytest.mark.asyncio
async def test_cb_b2b_pay_stars():
    callback = AsyncMock(spec=CallbackQuery)
    callback.message = AsyncMock(spec=Message)
    callback.message.answer_invoice = AsyncMock()
    callback.answer = AsyncMock()

    await b2b_handlers.cb_b2b_pay_stars(callback)
    callback.message.answer_invoice.assert_called_once()
    _, kwargs = callback.message.answer_invoice.call_args
    assert kwargs["currency"] == "XTR"
    assert kwargs["provider_token"] == ""


@pytest.mark.asyncio
async def test_pre_checkout_query():
    query = AsyncMock(spec=PreCheckoutQuery)
    query.answer = AsyncMock()

    await b2b_handlers.cb_pre_checkout(query)
    query.answer.assert_called_with(ok=True)


@pytest.mark.asyncio
async def test_msg_successful_payment(session: AsyncSession):
    message = AsyncMock(spec=Message)
    message.from_user = MagicMock(spec=User)
    message.from_user.id = 12345
    message.successful_payment = MagicMock(spec=SuccessfulPayment)
    message.successful_payment.telegram_payment_charge_id = "charge_123"
    message.answer = AsyncMock()

    with patch(
        "bot.handlers.b2b.b2b_service.create_b2b_license", new_callable=AsyncMock
    ) as mock_create:
        mock_create.return_value = {"license_id": "lic_123", "expires_at": datetime(2027, 5, 11)}
        await b2b_handlers.msg_successful_payment(message, session)

        mock_create.assert_called_with(session, user_id=12345, charge_id="charge_123")
        message.answer.assert_called()
        assert "activated" in message.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_cb_b2b_buy() -> None:
    """cb_b2b_buy shows payment method selection."""
    callback = AsyncMock(spec=CallbackQuery)
    callback.message = AsyncMock(spec=Message)
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()

    await b2b_handlers.cb_b2b_buy(callback)
    callback.message.edit_text.assert_called_once()
    assert "payment method" in callback.message.edit_text.call_args[0][0].lower()


@pytest.mark.asyncio
async def test_cb_b2b_pay_ton(session: AsyncSession) -> None:
    """cb_b2b_pay_ton generates TON invoice and displays memo."""
    callback = AsyncMock(spec=CallbackQuery)
    callback.from_user = MagicMock()
    callback.from_user.id = 12345
    callback.message = AsyncMock(spec=Message)
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()

    with (
        patch("services.b2b_service.get_ton_license_price", return_value=1.0),
        patch("services.b2b_service.create_ton_invoice", return_value={"memo": "TEST_MEMO"}),
    ):
        await b2b_handlers.cb_b2b_pay_ton(callback, session)
        callback.message.edit_text.assert_called_once()
        assert "TEST_MEMO" in callback.message.edit_text.call_args[0][0]


@pytest.mark.asyncio
async def test_cb_b2b_spawn(session: AsyncSession) -> None:
    """cb_b2b_spawn prompts user to create a bot via BotFather."""
    callback = AsyncMock(spec=CallbackQuery)
    callback.from_user = MagicMock()
    callback.from_user.id = 12345
    callback.message = AsyncMock(spec=Message)
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()

    with (
        patch("services.b2b_service.get_active_license", return_value={"license_id": "lic_123"}),
        patch("bot.handlers.b2b.settings.MASTER_BOT_USERNAME", "p2p_master_bot"),
    ):
        await b2b_handlers.cb_b2b_spawn(callback, session)
        callback.message.edit_text.assert_called_once()
        assert "BotFather" in callback.message.edit_text.call_args[0][0]
        callback.answer.assert_called_once()


@pytest.mark.asyncio
async def test_cb_b2b_customize_no_license(session: AsyncSession) -> None:
    callback = AsyncMock(spec=CallbackQuery)
    callback.message = AsyncMock(spec=Message)
    callback.from_user = MagicMock()
    callback.from_user.id = 123
    callback.answer = AsyncMock()

    with patch("bot.handlers.b2b.b2b_service.get_active_license", return_value=None):
        await b2b_handlers.cb_b2b_customize(callback, session)
        callback.answer.assert_called_with("❌ Active license required.", show_alert=True)


@pytest.mark.asyncio
async def test_cb_b2b_customize_with_license(session: AsyncSession) -> None:
    callback = AsyncMock(spec=CallbackQuery)
    callback.message = AsyncMock(spec=Message)
    callback.from_user = MagicMock()
    callback.from_user.id = 123
    callback.answer = AsyncMock()
    callback.message.edit_text = AsyncMock()

    with patch(
        "bot.handlers.b2b.b2b_service.get_active_license",
        return_value={"branding": {"bot": {"name": "Test"}}},
    ):
        await b2b_handlers.cb_b2b_customize(callback, session)
        callback.message.edit_text.assert_called_once()
        assert "Test" in callback.message.edit_text.call_args[0][0]


@pytest.mark.asyncio
async def test_cb_b2b_customize_field() -> None:
    from aiogram.fsm.context import FSMContext

    callback = AsyncMock(spec=CallbackQuery)
    callback.message = AsyncMock(spec=Message)
    callback.data = "b2b:edit:bot.name"
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()
    state = AsyncMock(spec=FSMContext)

    await b2b_handlers.cb_b2b_customize_field(callback, state)
    state.set_state.assert_called_once()
    state.update_data.assert_called_with(field_path="bot.name")
    callback.message.edit_text.assert_called_once()
    assert "Bot Name" in callback.message.edit_text.call_args[0][0]


@pytest.mark.asyncio
async def test_msg_b2b_branding_value_empty(session: AsyncSession) -> None:
    from aiogram.fsm.context import FSMContext

    message = AsyncMock(spec=Message)
    message.text = "   "
    state = AsyncMock(spec=FSMContext)
    state.get_data.return_value = {"field_path": "bot.name"}
    message.answer = AsyncMock()

    await b2b_handlers.msg_b2b_branding_value(message, state, session)
    message.answer.assert_called_with("❌ Value cannot be empty.")


@pytest.mark.asyncio
async def test_msg_b2b_branding_value_invalid_handle(session: AsyncSession) -> None:
    from aiogram.fsm.context import FSMContext

    message = AsyncMock(spec=Message)
    message.text = "invalid"
    state = AsyncMock(spec=FSMContext)
    state.get_data.return_value = {"field_path": "bot.support_handle"}
    message.answer = AsyncMock()

    await b2b_handlers.msg_b2b_branding_value(message, state, session)
    message.answer.assert_called_with("❌ Support handle must start with @")


@pytest.mark.asyncio
async def test_msg_b2b_branding_value_success(session: AsyncSession) -> None:
    from aiogram.fsm.context import FSMContext

    message = AsyncMock(spec=Message)
    message.text = "New Name"
    message.from_user = MagicMock()
    message.from_user.id = 123
    state = AsyncMock(spec=FSMContext)
    state.get_data.return_value = {"field_path": "bot.name"}
    message.answer = AsyncMock()

    with (
        patch(
            "bot.handlers.b2b.b2b_service.get_active_license", return_value={"license_id": "123"}
        ),
        patch(
            "bot.handlers.b2b.b2b_service.update_license_branding", new_callable=AsyncMock
        ) as mock_update,
    ):
        await b2b_handlers.msg_b2b_branding_value(message, state, session)
        mock_update.assert_called_with(session, "123", "bot.name", "New Name")
        state.clear.assert_called_once()


@pytest.mark.asyncio
async def test_handle_managed_bot_created_success(session: AsyncSession) -> None:
    from services.bot_spawner import BotSpawnerService

    message = AsyncMock(spec=Message)
    message.managed_bot_created = MagicMock()
    message.managed_bot_created.bot_id = 999
    message.managed_bot_created.bot_username = "new_bot"
    message.from_user = MagicMock()
    message.from_user.id = 123
    message.bot = AsyncMock()
    message.bot.get_managed_bot_token.return_value = MagicMock(token="123:abc")
    message.answer = AsyncMock()
    bot_spawner = AsyncMock(spec=BotSpawnerService)

    with patch(
        "bot.handlers.b2b.b2b_service.get_active_license", return_value={"license_id": "123"}
    ):
        await b2b_handlers.handle_managed_bot_created(message, session, bot_spawner)
        bot_spawner.update_bot_token.assert_called_with(session, "123", "123:abc")
        assert "Successfully Spawned" in message.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_handle_managed_bot_created_no_license(session: AsyncSession) -> None:
    from services.bot_spawner import BotSpawnerService

    message = AsyncMock(spec=Message)
    message.managed_bot_created = MagicMock()
    message.from_user = MagicMock()
    message.from_user.id = 123
    message.answer = AsyncMock()
    bot_spawner = AsyncMock(spec=BotSpawnerService)

    with patch("bot.handlers.b2b.b2b_service.get_active_license", return_value=None):
        await b2b_handlers.handle_managed_bot_created(message, session, bot_spawner)
        message.answer.assert_called_with("❌ License not found. Please contact support.")
