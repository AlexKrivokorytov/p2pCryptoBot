"""Tests for profile handlers and user service."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.handlers import profile as profile_handlers
from db.models.user import User
from services import user_service

pytestmark = pytest.mark.unit

_MOCK_REPUTATION = {"total_reviews": 5, "positive_reviews": 4, "completion_rate": 80}


@pytest.mark.integration
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
@patch("bot.handlers.profile.get_or_create_user", new_callable=AsyncMock)
@patch(
    "bot.handlers.profile.MarketplaceService.get_user_reputation",
    new_callable=AsyncMock,
    return_value=_MOCK_REPUTATION,
)
async def test_cmd_profile(mock_reputation: AsyncMock, mock_get_profile: AsyncMock) -> None:
    """Test the profile command shows statistics."""
    session = AsyncMock(spec=AsyncSession)
    user = User(telegram_id=999, is_verified=True, total_trades=10, successful_trades=8)
    mock_get_profile.return_value = user

    mock_bot_me = MagicMock()
    mock_bot_me.username = "testbot"

    message = AsyncMock(spec=Message)
    message.from_user = MagicMock()
    message.from_user.id = 999
    message.answer = AsyncMock()
    message.bot = AsyncMock()
    message.bot.get_me = AsyncMock(return_value=mock_bot_me)

    await profile_handlers.cmd_profile(message, session)

    message.answer.assert_called_once()
    text = message.answer.call_args[0][0]
    assert "Your Profile" in text
    assert "10" in text
    assert "Verified" in text


@pytest.mark.asyncio
@patch("bot.handlers.profile.get_or_create_user", new_callable=AsyncMock)
@patch(
    "bot.handlers.profile.MarketplaceService.get_user_reputation",
    new_callable=AsyncMock,
    return_value=_MOCK_REPUTATION,
)
async def test_cb_profile(mock_reputation: AsyncMock, mock_get_profile: AsyncMock) -> None:
    """Test the profile callback shows statistics."""
    session = AsyncMock(spec=AsyncSession)
    user = User(telegram_id=999, is_verified=False, total_trades=0, successful_trades=0)
    mock_get_profile.return_value = user

    mock_bot_me = MagicMock()
    mock_bot_me.username = "testbot"

    callback = AsyncMock(spec=CallbackQuery)
    callback.from_user = MagicMock()
    callback.from_user.id = 999
    callback.message = AsyncMock(spec=Message)
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()
    callback.bot = AsyncMock()
    callback.bot.get_me = AsyncMock(return_value=mock_bot_me)

    await profile_handlers.cb_profile(callback, session)

    callback.message.edit_text.assert_called_once()
    text = callback.message.edit_text.call_args[0][0]
    assert "Unverified" in text
    callback.answer.assert_called_once()


@pytest.mark.asyncio
async def test_build_profile_text_none_user() -> None:
    """Should return 'Profile not found' if user is None."""
    session = MagicMock()
    from bot.handlers.profile import _build_profile_text

    text = await _build_profile_text(None, session, "testbot")
    assert "Profile not found" in text


@pytest.mark.asyncio
async def test_cmd_profile_no_from_user() -> None:
    """cmd_profile should return early if from_user is missing."""
    message = MagicMock()
    message.from_user = None
    message.bot = MagicMock()
    message.answer = AsyncMock()
    session = MagicMock()

    await profile_handlers.cmd_profile(message, session)
    message.answer.assert_not_awaited()


@pytest.mark.asyncio
async def test_cb_profile_no_from_user() -> None:
    """cb_profile should return early if from_user is None."""
    cb = MagicMock()
    cb.from_user = None
    cb.answer = AsyncMock()
    session = MagicMock()

    await profile_handlers.cb_profile(cb, session)
    cb.answer.assert_not_awaited()


@pytest.mark.asyncio
async def test_build_profile_text_unverified_zero_trades() -> None:
    """Unverified user with zero trades should show 0.0% success rate."""
    from bot.handlers.profile import _build_profile_text

    user = MagicMock()
    user.telegram_id = 456
    user.total_trades = 0
    user.successful_trades = 0
    user.is_verified = False

    session = MagicMock()

    with patch(
        "bot.handlers.profile.MarketplaceService.get_user_reputation",
        new_callable=AsyncMock,
    ) as mock_rep:
        mock_rep.return_value = {
            "total_reviews": 0,
            "positive_reviews": 0,
            "completion_rate": 100,
        }
        text = await _build_profile_text(user, session, "anotherbot")

    assert "Unverified" in text
    assert "0.0%" in text
