from unittest.mock import AsyncMock, patch

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, User

from bot.handlers.admin_sandbox import (
    cb_sandbox_add_usdt,
    cb_sandbox_force_status,
    cb_sandbox_lic_bypass,
    cb_sandbox_order_state,
    msg_sandbox_order_id,
)
from bot.states import AdminSandboxFSM

pytestmark = [pytest.mark.unit]


@pytest.fixture
def callback_query_admin():
    cb = AsyncMock(spec=CallbackQuery)
    cb.from_user = User(id=1, is_bot=False, first_name="Admin")
    cb.data = "dummy"
    cb.message = AsyncMock(spec=Message)
    cb.message.answer = AsyncMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    return cb


@pytest.fixture
def callback_query_user():
    cb = AsyncMock(spec=CallbackQuery)
    cb.from_user = User(id=999, is_bot=False, first_name="User")
    cb.data = "dummy"
    cb.message = AsyncMock(spec=Message)
    cb.message.answer = AsyncMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    return cb


@pytest.mark.asyncio
@patch("bot.handlers.admin_sandbox._is_admin", return_value=False)
async def test_cb_sandbox_lic_bypass_not_admin(mock_is_admin, callback_query_user):
    await cb_sandbox_lic_bypass(callback_query_user, session=AsyncMock())
    mock_is_admin.assert_called_once_with(999)
    callback_query_user.message.answer.assert_not_called()


@pytest.mark.asyncio
@patch("bot.handlers.admin_sandbox._is_admin", return_value=False)
async def test_cb_sandbox_add_usdt_not_admin(mock_is_admin, callback_query_user):
    await cb_sandbox_add_usdt(callback_query_user, session=AsyncMock())
    callback_query_user.message.answer.assert_not_called()


@pytest.mark.asyncio
@patch("bot.handlers.admin_sandbox._is_admin", return_value=False)
async def test_cb_sandbox_order_state_not_admin(mock_is_admin, callback_query_user):
    state = AsyncMock(spec=FSMContext)
    await cb_sandbox_order_state(callback_query_user, state)
    state.set_state.assert_not_called()


@pytest.mark.asyncio
@patch("bot.handlers.admin_sandbox._is_admin", return_value=True)
async def test_cb_sandbox_order_state_admin(mock_is_admin, callback_query_admin):
    state = AsyncMock(spec=FSMContext)
    state.set_state = AsyncMock()
    await cb_sandbox_order_state(callback_query_admin, state)
    state.set_state.assert_called_once_with(AdminSandboxFSM.enter_order_id)
    callback_query_admin.message.answer.assert_called_once()


@pytest.mark.asyncio
async def test_msg_sandbox_order_id_invalid():
    message = AsyncMock(spec=Message)
    message.answer = AsyncMock()
    message.text = "short"
    state = AsyncMock(spec=FSMContext)
    state.update_data = AsyncMock()
    await msg_sandbox_order_id(message, state)
    message.answer.assert_called_once_with(
        "❌ Invalid Order ID. Please enter at least 8 characters."
    )
    state.update_data.assert_not_called()


@pytest.mark.asyncio
async def test_msg_sandbox_order_id_valid():
    message = AsyncMock(spec=Message)
    message.answer = AsyncMock()
    message.text = "12345678-abcd"
    state = AsyncMock(spec=FSMContext)
    state.update_data = AsyncMock()
    state.set_state = AsyncMock()
    await msg_sandbox_order_id(message, state)
    state.update_data.assert_called_once_with(sandbox_order_id="12345678-abcd")
    state.set_state.assert_called_once_with(AdminSandboxFSM.choose_status)


@pytest.mark.asyncio
@patch("bot.handlers.admin_sandbox.admin_sandbox_service.force_order_status")
async def test_cb_sandbox_force_status(mock_force_status, callback_query_admin):
    callback_query_admin.data = "admin:sandbox:force:12345678:fiat_sent"
    state = AsyncMock(spec=FSMContext)
    state.clear = AsyncMock()
    session = AsyncMock()

    await cb_sandbox_force_status(callback_query_admin, state, session)

    mock_force_status.assert_called_once_with(
        session, admin_id=1, order_id="12345678", new_status="fiat_sent"
    )
    state.clear.assert_called_once()
    callback_query_admin.message.edit_text.assert_called_once()
