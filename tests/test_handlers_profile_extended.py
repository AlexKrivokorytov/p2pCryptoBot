"""Tests for bot/handlers/profile.py — profile display handlers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.handlers.profile import _build_profile_text, cb_profile, cmd_profile

# ── _build_profile_text ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_build_profile_text_none_user() -> None:
    """Should return 'Profile not found' if user is None."""
    session = MagicMock()
    text = await _build_profile_text(None, session, "testbot")
    assert "Profile not found" in text


@pytest.mark.asyncio
async def test_build_profile_text_with_user() -> None:
    """Should return profile text with trade stats and reputation."""
    user = MagicMock()
    user.telegram_id = 123
    user.total_trades = 10
    user.successful_trades = 8
    user.is_verified = True

    session = MagicMock()

    with patch(
        "bot.handlers.profile.MarketplaceService.get_user_reputation",
        new_callable=AsyncMock,
    ) as mock_rep:
        mock_rep.return_value = {
            "total_reviews": 5,
            "positive_reviews": 4,
            "completion_rate": 80,
        }
        text = await _build_profile_text(user, session, "mybot")

    assert "123" in text
    assert "10" in text  # total trades
    assert "80.0%" in text  # success rate
    assert "mybot" in text  # referral link
    assert "Verified" in text


@pytest.mark.asyncio
async def test_build_profile_text_unverified_zero_trades() -> None:
    """Unverified user with zero trades should show 0% success rate."""
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


# ── cmd_profile ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cmd_profile_no_from_user() -> None:
    """cmd_profile should return early if from_user is missing."""
    message = MagicMock()
    message.from_user = None
    message.bot = MagicMock()
    message.answer = AsyncMock()
    session = MagicMock()

    await cmd_profile(message, session)
    message.answer.assert_not_awaited()


@pytest.mark.asyncio
async def test_cmd_profile_no_bot() -> None:
    """cmd_profile should return early if message.bot is missing."""
    message = MagicMock()
    message.from_user = MagicMock()
    message.bot = None
    message.answer = AsyncMock()
    session = MagicMock()

    await cmd_profile(message, session)
    message.answer.assert_not_awaited()


@pytest.mark.asyncio
async def test_cmd_profile_success() -> None:
    """cmd_profile should respond with profile text."""
    message = MagicMock()
    message.from_user = MagicMock()
    message.from_user.id = 123
    message.bot = MagicMock()
    message.bot.get_me = AsyncMock(return_value=MagicMock(username="testbot"))
    message.answer = AsyncMock()

    session = MagicMock()

    user = MagicMock()
    user.telegram_id = 123
    user.total_trades = 5
    user.successful_trades = 4
    user.is_verified = True

    with (
        patch(
            "bot.handlers.profile.get_user_profile",
            new_callable=AsyncMock,
            return_value=user,
        ),
        patch(
            "bot.handlers.profile.MarketplaceService.get_user_reputation",
            new_callable=AsyncMock,
            return_value={"total_reviews": 2, "positive_reviews": 2, "completion_rate": 100},
        ),
    ):
        await cmd_profile(message, session)

    message.answer.assert_awaited_once()


# ── cb_profile ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cb_profile_no_from_user() -> None:
    """cb_profile should return early if from_user is None."""
    cb = MagicMock()
    cb.from_user = None
    cb.message = MagicMock()
    cb.bot = MagicMock()
    cb.answer = AsyncMock()
    session = MagicMock()

    await cb_profile(cb, session)
    cb.answer.assert_not_awaited()


@pytest.mark.asyncio
async def test_cb_profile_message_not_message_type() -> None:
    """cb_profile should return early if message is not a Message instance."""

    cb = MagicMock()
    cb.from_user = MagicMock()
    cb.message = "not a Message object"  # not an instance of Message
    cb.bot = MagicMock()
    cb.answer = AsyncMock()
    session = MagicMock()

    await cb_profile(cb, session)
    cb.answer.assert_not_awaited()


@pytest.mark.asyncio
async def test_cb_profile_success() -> None:
    """cb_profile should show profile text via edit_text."""
    from aiogram.types import Message

    cb = MagicMock()
    cb.from_user = MagicMock()
    cb.from_user.id = 123
    cb.bot = MagicMock()
    cb.bot.get_me = AsyncMock(return_value=MagicMock(username="testbot"))
    cb.message = MagicMock(spec=Message)
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()

    session = MagicMock()
    user = MagicMock()
    user.telegram_id = 123
    user.total_trades = 3
    user.successful_trades = 3
    user.is_verified = False

    with (
        patch(
            "bot.handlers.profile.get_user_profile",
            new_callable=AsyncMock,
            return_value=user,
        ),
        patch(
            "bot.handlers.profile.MarketplaceService.get_user_reputation",
            new_callable=AsyncMock,
            return_value={"total_reviews": 0, "positive_reviews": 0, "completion_rate": 100},
        ),
    ):
        await cb_profile(cb, session)

    cb.message.edit_text.assert_awaited_once()
    cb.answer.assert_awaited_once()
