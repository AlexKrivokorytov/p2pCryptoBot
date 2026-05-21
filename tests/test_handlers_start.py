"""Tests for start handlers."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.handlers import start as start_handlers
from db.models.user import User

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_cmd_start_new_user(session: AsyncSession) -> None:
    """Test /start command creates a new user."""
    message = AsyncMock()
    message.from_user.id = 12345
    message.from_user.username = "new_user"
    message.from_user.first_name = "New"

    await start_handlers.cmd_start(message, session)

    # Verify user was created in DB
    result = await session.execute(select(User).where(User.telegram_id == 12345))
    user = result.scalar_one_or_none()

    assert user is not None
    assert user.username == "new_user"
    assert user.first_name == "New"

    message.answer.assert_called_once()
    assert "Welcome to" in message.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_cmd_start_existing_user(session: AsyncSession) -> None:
    """Test /start command with existing user."""
    # Create user first
    async with session.begin():
        session.add(User(telegram_id=12345, username="old_user", first_name="Old"))

    message = AsyncMock()
    message.from_user.id = 12345
    message.from_user.first_name = "Old"

    await start_handlers.cmd_start(message, session)

    # Should not create duplicate
    message.answer.assert_called_once()
    assert "Welcome to" in message.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_cb_main_menu() -> None:
    """Test main menu callback."""
    from aiogram.types import CallbackQuery, Message

    callback = AsyncMock(spec=CallbackQuery)
    callback.message = AsyncMock(spec=Message)
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()

    await start_handlers.cb_main_menu(callback)

    callback.message.edit_text.assert_called_once()
    # It has an emoji now: "🏠 <b>Main Menu</b>"
    args, _ = callback.message.edit_text.call_args
    assert "Main Menu" in args[0]
    callback.answer.assert_called_once()


@pytest.mark.asyncio
async def test_cb_help() -> None:
    """Test help callback."""
    from aiogram.types import CallbackQuery, Message

    callback = AsyncMock(spec=CallbackQuery)
    callback.message = AsyncMock(spec=Message)
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()

    await start_handlers.cb_help(callback)

    # It calls edit_text, not answer
    callback.message.edit_text.assert_called_once()
    args, _ = callback.message.edit_text.call_args
    assert "How P2P works" in args[0]
    callback.answer.assert_called_once()


@pytest.mark.asyncio
async def test_cmd_start_no_from_user() -> None:
    """cmd_start returns early and does nothing when message.from_user is None."""
    message = AsyncMock()
    message.from_user = None
    session = AsyncMock()

    await start_handlers.cmd_start(message, session)

    # Must not attempt to answer or touch DB
    message.answer.assert_not_called()
    session.begin.assert_not_called()
