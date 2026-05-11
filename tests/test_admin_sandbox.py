from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.types import CallbackQuery, Message
from aiogram.types import User as TgUser

from bot.handlers.admin_sandbox import cb_sandbox_add_usdt, cb_sandbox_lic_bypass, cb_sandbox_menu


@pytest.fixture
def admin_user():
    return TgUser(id=123, is_bot=False, first_name="Admin")


@pytest.fixture
def regular_user():
    return TgUser(id=456, is_bot=False, first_name="User")


@pytest.mark.asyncio
async def test_cb_sandbox_menu_authorized(admin_user):
    callback = AsyncMock(spec=CallbackQuery)
    callback.from_user = admin_user
    callback.message = AsyncMock(spec=Message)
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()

    with patch("bot.handlers.admin_sandbox.settings.ADMIN_IDS", [123]):
        await cb_sandbox_menu(callback)
        callback.message.edit_text.assert_called_once()
        callback.answer.assert_called_once()


@pytest.mark.asyncio
async def test_cb_sandbox_menu_unauthorized(regular_user):
    callback = AsyncMock(spec=CallbackQuery)
    callback.from_user = regular_user
    callback.answer = AsyncMock()

    with patch("bot.handlers.admin_sandbox.settings.ADMIN_IDS", [123]):
        await cb_sandbox_menu(callback)
        callback.answer.assert_called_with("🚫 Unauthorized.", show_alert=True)


@pytest.mark.asyncio
async def test_cb_sandbox_lic_bypass(admin_user, session):
    callback = AsyncMock(spec=CallbackQuery)
    callback.from_user = admin_user
    callback.message = AsyncMock(spec=Message)
    callback.message.answer = AsyncMock()
    callback.answer = AsyncMock()

    mock_lic = MagicMock()
    mock_lic.id = "lic_123"
    mock_lic.expires_at = MagicMock()
    mock_lic.expires_at.strftime.return_value = "2026-05-11"

    with (
        patch("bot.handlers.admin_sandbox.settings.ADMIN_IDS", [123]),
        patch("services.admin_sandbox_service.activate_license_bypass", return_value=mock_lic),
    ):
        await cb_sandbox_lic_bypass(callback, session)
        callback.message.answer.assert_called()
        callback.answer.assert_called_with("License bypassed!")


@pytest.mark.asyncio
async def test_cb_sandbox_add_usdt(admin_user, session):
    callback = AsyncMock(spec=CallbackQuery)
    callback.from_user = admin_user
    callback.message = AsyncMock(spec=Message)
    callback.message.answer = AsyncMock()
    callback.answer = AsyncMock()

    with (
        patch("bot.handlers.admin_sandbox.settings.ADMIN_IDS", [123]),
        patch("services.admin_sandbox_service.inject_test_balance", return_value=None),
    ):
        await cb_sandbox_add_usdt(callback, session)
        callback.message.answer.assert_called()
        callback.answer.assert_called_with("Balance injected!")
