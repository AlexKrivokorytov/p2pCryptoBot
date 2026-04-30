"""Tests for profile handlers and user service."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.handlers import profile as profile_handlers
from db.models.user import User
from services import user_service


@pytest.mark.asyncio
async def test_user_service_increment_stats(engine) -> None:
    """Test incrementing user trade statistics."""
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session, session.begin():
        user = User(telegram_id=999, username="tester", total_trades=0, successful_trades=0)
        session.add(user)

    async with factory() as session, session.begin():
        # Successful trade
        await user_service.increment_user_trade_stats(session, 999, successful=True)
        # Failed trade
        await user_service.increment_user_trade_stats(session, 999, successful=False)

    async with factory() as session:
        user = await user_service.get_user_profile(session, 999)
        assert user is not None
        assert user.total_trades == 2
        assert user.successful_trades == 1


@pytest.mark.asyncio
@patch("bot.handlers.profile.get_user_profile", new_callable=AsyncMock)
async def test_cmd_profile(mock_get_profile: AsyncMock, session: AsyncSession) -> None:
    """Test the profile command shows statistics."""
    user = User(telegram_id=999, is_verified=True, total_trades=10, successful_trades=8)
    mock_get_profile.return_value = user

    message = AsyncMock()
    message.from_user.id = 999

    await profile_handlers.cmd_profile(message, session)

    message.answer.assert_called_once()
    text = message.answer.call_args[0][0]
    assert "Your Profile" in text
    assert "80.0%" in text
    assert "10" in text
    assert "Verified" in text


@pytest.mark.asyncio
@patch("bot.handlers.profile.get_user_profile", new_callable=AsyncMock)
async def test_cb_profile(mock_get_profile: AsyncMock, session: AsyncSession) -> None:
    """Test the profile callback shows statistics."""
    user = User(telegram_id=999, is_verified=False, total_trades=0, successful_trades=0)
    mock_get_profile.return_value = user

    callback = AsyncMock(spec=CallbackQuery)
    callback.from_user = MagicMock()
    callback.from_user.id = 999
    callback.message = AsyncMock(spec=Message)

    await profile_handlers.cb_profile(callback, session)

    callback.message.edit_text.assert_called_once()
    text = callback.message.edit_text.call_args[0][0]
    assert "0.0%" in text
    assert "Unverified" in text
    callback.answer.assert_called_once()
