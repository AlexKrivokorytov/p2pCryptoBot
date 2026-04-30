"""Tests for notification service."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.methods import SendMessage

from services import notification_service


@pytest.mark.asyncio
async def test_notify_maker_taker_found_success() -> None:
    """Successfully notifies the maker about a new taker."""
    bot = AsyncMock(spec=Bot)

    result = await notification_service.notify_maker_taker_found(
        bot, maker_id=123, taker_username="testuser", order_id="uuid-1234"
    )

    assert result is True
    bot.send_message.assert_called_once()
    args = bot.send_message.call_args[0]
    assert args[0] == 123
    assert "@testuser" in args[1]
    assert "uuid-123" in args[1]


@pytest.mark.asyncio
async def test_notify_maker_taker_found_no_username() -> None:
    """Handles taker without a username gracefully."""
    bot = AsyncMock(spec=Bot)

    result = await notification_service.notify_maker_taker_found(
        bot, maker_id=123, taker_username=None, order_id="uuid-1234"
    )

    assert result is True
    args = bot.send_message.call_args[0]
    assert "A user" in args[1]


@pytest.mark.asyncio
async def test_notify_maker_taker_found_error() -> None:
    """Handles TelegramAPIError gracefully."""
    bot = AsyncMock(spec=Bot)
    bot.send_message.side_effect = TelegramAPIError(
        method=SendMessage(chat_id=1, text=""), message="Forbidden: bot was blocked by the user"
    )

    result = await notification_service.notify_maker_taker_found(
        bot, maker_id=123, taker_username="test", order_id="uuid-1234"
    )

    assert result is False


@pytest.mark.asyncio
async def test_notify_maker_fiat_sent_success() -> None:
    """Successfully notifies the maker about fiat being sent."""
    bot = AsyncMock(spec=Bot)

    result = await notification_service.notify_maker_fiat_sent(
        bot, maker_id=123, order_id="uuid-1234"
    )

    assert result is True
    bot.send_message.assert_called_once()
    args = bot.send_message.call_args[0]
    assert args[0] == 123
    assert "uuid-123" in args[1]


@pytest.mark.asyncio
async def test_notify_maker_fiat_sent_error() -> None:
    """Handles TelegramAPIError gracefully during fiat sent notification."""
    bot = AsyncMock(spec=Bot)
    bot.send_message.side_effect = TelegramAPIError(
        method=SendMessage(chat_id=1, text=""), message="Forbidden: bot was blocked by the user"
    )

    result = await notification_service.notify_maker_fiat_sent(
        bot, maker_id=123, order_id="uuid-1234"
    )

    assert result is False
