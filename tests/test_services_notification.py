"""Tests for notification service."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.methods import SendMessage

from services import notification_service

pytestmark = pytest.mark.unit


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


@pytest.mark.asyncio
async def test_notify_taker_escrow_released_success() -> None:
    """Taker receives notification about released escrow."""
    bot = AsyncMock(spec=Bot)
    result = await notification_service.notify_taker_escrow_released(
        bot, taker_id=123, order_id="uuid-1", asset="USDT", amount=10.5
    )
    assert result is True
    bot.send_message.assert_called_once()
    args = bot.send_message.call_args[0]
    assert args[0] == 123
    assert "Released" in args[1]
    assert "10.5 USDT" in args[1]


@pytest.mark.asyncio
async def test_notify_taker_escrow_released_error() -> None:
    """Returns False on TelegramAPIError."""
    bot = AsyncMock(spec=Bot)
    bot.send_message.side_effect = TelegramAPIError(
        method=SendMessage(chat_id=1, text=""), message="Forbidden"
    )
    result = await notification_service.notify_taker_escrow_released(
        bot, taker_id=123, order_id="uuid-1", asset="USDT", amount=10.5
    )
    assert result is False


@pytest.mark.asyncio
async def test_notify_dispute_opened_both_parties() -> None:
    """Bot sends messages to both maker and taker."""
    bot = AsyncMock(spec=Bot)
    await notification_service.notify_dispute_opened(
        bot, maker_id=111, taker_id=222, order_id="uuid-1", reason="Payment not received"
    )
    assert bot.send_message.call_count == 2
    calls = bot.send_message.call_args_list
    target_ids = [c.args[0] for c in calls]
    assert 111 in target_ids
    assert 222 in target_ids
    assert "Dispute Opened" in calls[0].args[1]
    assert "Payment not received" in calls[0].args[1]


@pytest.mark.asyncio
async def test_notify_dispute_opened_no_taker() -> None:
    """Only maker is notified if taker_id is None."""
    bot = AsyncMock(spec=Bot)
    await notification_service.notify_dispute_opened(
        bot, maker_id=111, taker_id=None, order_id="uuid-1", reason="Timeout"
    )
    bot.send_message.assert_called_once()
    assert bot.send_message.call_args.args[0] == 111


@pytest.mark.asyncio
async def test_notify_order_expired_success() -> None:
    """Maker receives notification about expired ad."""
    bot = AsyncMock(spec=Bot)
    # Mock main_menu_keyboard to avoid branding dependency in simple test
    with patch("bot.keyboards.main_menu_keyboard", return_value=None):
        result = await notification_service.notify_order_expired(
            bot, maker_id=111, order_id="uuid-1", asset="BTC"
        )
    assert result is True
    bot.send_message.assert_called_once()
    assert bot.send_message.call_args.args[0] == 111
    assert "Ad Expired" in bot.send_message.call_args.args[1]
    assert "BTC" in bot.send_message.call_args.args[1]


@pytest.mark.asyncio
async def test_notify_order_expired_error() -> None:
    """Returns False on TelegramAPIError."""
    bot = AsyncMock(spec=Bot)
    bot.send_message.side_effect = TelegramAPIError(
        method=SendMessage(chat_id=1, text=""), message="Retry later"
    )
    # Mock main_menu_keyboard
    with patch("bot.keyboards.main_menu_keyboard", return_value=None):
        result = await notification_service.notify_order_expired(
            bot, maker_id=111, order_id="uuid-1", asset="BTC"
        )
    assert result is False
