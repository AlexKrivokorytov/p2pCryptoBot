"""Tests for notification service."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.methods import SendMessage

from services import notification_service

pytestmark = pytest.mark.unit

# Sample branding for testing
MOCK_BRANDING = {
    "notifications": {
        "taker_found": "Started {order_id_short} {taker_display}",
        "fiat_sent": "Fiat sent {order_id_short}",
        "escrow_released": "Released {order_id_short} {amount} {asset}",
        "dispute_opened": "Dispute Opened {order_id_short} {reason}",
        "dispute_resolved": "Dispute Resolved {order_id_short} {decision} {status}",
        "order_expired": "Ad Expired {order_id_short} {asset}",
        "escrow_refunded": "Escrow Refunded {order_id_short} {amount} {asset}",
    }
}


@pytest.fixture
def mock_branding():
    """Patch get_branding to return test templates."""
    with patch("services.notification_service.get_branding", return_value=MOCK_BRANDING):
        yield MOCK_BRANDING


@pytest.mark.asyncio
async def test_notify_maker_taker_found_success(mock_branding) -> None:
    """Successfully notifies the maker about a new taker."""
    bot = AsyncMock(spec=Bot)

    result = await notification_service.notify_maker_taker_found(
        bot, maker_id=123, taker_username="testuser", order_id="uuid-12345678"
    )

    assert result is True
    bot.send_message.assert_called_once()
    args, kwargs = bot.send_message.call_args
    assert args[0] == 123
    assert "@testuser" in args[1]
    assert "uuid-123" in args[1]


@pytest.mark.asyncio
async def test_notify_maker_taker_found_no_username(mock_branding) -> None:
    """Handles taker without a username gracefully."""
    bot = AsyncMock(spec=Bot)

    result = await notification_service.notify_maker_taker_found(
        bot, maker_id=123, taker_username=None, order_id="uuid-12345678"
    )

    assert result is True
    args, kwargs = bot.send_message.call_args
    assert "A user" in args[1]


@pytest.mark.asyncio
async def test_notify_maker_taker_found_error(mock_branding) -> None:
    """Handles TelegramAPIError gracefully."""
    bot = AsyncMock(spec=Bot)
    bot.send_message.side_effect = TelegramAPIError(
        method=SendMessage(chat_id=1, text=""), message="Forbidden: bot was blocked by the user"
    )

    result = await notification_service.notify_maker_taker_found(
        bot, maker_id=123, taker_username="test", order_id="uuid-12345678"
    )

    assert result is False


@pytest.mark.asyncio
async def test_notify_maker_fiat_sent_success(mock_branding) -> None:
    """Successfully notifies the maker about fiat being sent."""
    bot = AsyncMock(spec=Bot)

    result = await notification_service.notify_maker_fiat_sent(
        bot, maker_id=123, order_id="uuid-12345678"
    )

    assert result is True
    bot.send_message.assert_called_once()
    args, kwargs = bot.send_message.call_args
    assert args[0] == 123
    assert "uuid-123" in args[1]


@pytest.mark.asyncio
async def test_notify_maker_fiat_sent_error(mock_branding) -> None:
    """Handles TelegramAPIError gracefully during fiat sent notification."""
    bot = AsyncMock(spec=Bot)
    bot.send_message.side_effect = TelegramAPIError(
        method=SendMessage(chat_id=1, text=""), message="Forbidden: bot was blocked by the user"
    )

    result = await notification_service.notify_maker_fiat_sent(
        bot, maker_id=123, order_id="uuid-12345678"
    )

    assert result is False


@pytest.mark.asyncio
async def test_notify_taker_escrow_released_success(mock_branding) -> None:
    """Taker receives notification about released escrow."""
    bot = AsyncMock(spec=Bot)
    result = await notification_service.notify_taker_escrow_released(
        bot, taker_id=123, order_id="uuid-12345678", asset="USDT", amount=10.5
    )
    assert result is True
    bot.send_message.assert_called_once()
    args, kwargs = bot.send_message.call_args
    assert args[0] == 123
    assert "Released" in args[1]
    assert "10.5 USDT" in args[1]


@pytest.mark.asyncio
async def test_notify_taker_escrow_released_error(mock_branding) -> None:
    """Returns False on TelegramAPIError."""
    bot = AsyncMock(spec=Bot)
    bot.send_message.side_effect = TelegramAPIError(
        method=SendMessage(chat_id=1, text=""), message="Forbidden"
    )
    result = await notification_service.notify_taker_escrow_released(
        bot, taker_id=123, order_id="uuid-12345678", asset="USDT", amount=10.5
    )
    assert result is False


@pytest.mark.asyncio
async def test_notify_dispute_opened_both_parties(mock_branding) -> None:
    """Bot sends messages to both maker and taker."""
    bot = AsyncMock(spec=Bot)
    await notification_service.notify_dispute_opened(
        bot, maker_id=111, taker_id=222, order_id="uuid-12345678", reason="Payment not received"
    )
    assert bot.send_message.call_count == 2
    calls = bot.send_message.call_args_list
    target_ids = [c.args[0] for c in calls]
    assert 111 in target_ids
    assert 222 in target_ids
    assert "Dispute Opened" in calls[0].args[1]
    assert "Payment not received" in calls[0].args[1]


@pytest.mark.asyncio
async def test_notify_dispute_opened_no_taker(mock_branding) -> None:
    """Only maker is notified if taker_id is None."""
    bot = AsyncMock(spec=Bot)
    await notification_service.notify_dispute_opened(
        bot, maker_id=111, taker_id=None, order_id="uuid-12345678", reason="Timeout"
    )
    bot.send_message.assert_called_once()
    assert bot.send_message.call_args.args[0] == 111


@pytest.mark.asyncio
async def test_notify_dispute_resolved_success(mock_branding) -> None:
    """Both parties receive resolution notification."""
    bot = AsyncMock(spec=Bot)
    await notification_service.notify_dispute_resolved(
        bot,
        maker_id=111,
        taker_id=222,
        order_id="uuid-12345678",
        decision="taker_wins",
        status="completed",
    )
    assert bot.send_message.call_count == 2
    args, kwargs = bot.send_message.call_args
    assert "Dispute Resolved" in args[1]
    assert "Taker Wins" in args[1]


@pytest.mark.asyncio
async def test_notify_escrow_refunded_success(mock_branding) -> None:
    """Maker receives notification about refunded escrow."""
    bot = AsyncMock(spec=Bot)
    result = await notification_service.notify_escrow_refunded(
        bot, maker_id=111, order_id="uuid-12345678", asset="USDT", amount=10.5
    )
    assert result is True
    bot.send_message.assert_called_once()
    assert bot.send_message.call_args.args[0] == 111
    assert "Escrow Refunded" in bot.send_message.call_args.args[1]


@pytest.mark.asyncio
async def test_notify_order_expired_success(mock_branding) -> None:
    """Maker receives notification about expired ad."""
    bot = AsyncMock(spec=Bot)
    result = await notification_service.notify_order_expired(
        bot, maker_id=111, order_id="uuid-12345678", asset="BTC"
    )
    assert result is True
    bot.send_message.assert_called_once()
    assert bot.send_message.call_args.args[0] == 111
    assert "Ad Expired" in bot.send_message.call_args.args[1]
    assert "BTC" in bot.send_message.call_args.args[1]


@pytest.mark.asyncio
async def test_notify_order_expired_error(mock_branding) -> None:
    """Returns False on TelegramAPIError."""
    bot = AsyncMock(spec=Bot)
    bot.send_message.side_effect = TelegramAPIError(
        method=SendMessage(chat_id=1, text=""), message="Retry later"
    )
    result = await notification_service.notify_order_expired(
        bot, maker_id=111, order_id="uuid-12345678", asset="BTC"
    )
    assert result is False


@pytest.mark.asyncio
async def test_notify_dispute_opened_error(mock_branding) -> None:
    bot = AsyncMock(spec=Bot)
    bot.send_message.side_effect = TelegramAPIError(
        method=SendMessage(chat_id=1, text=""), message="Retry later"
    )
    await notification_service.notify_dispute_opened(
        bot, maker_id=111, taker_id=222, order_id="uuid-123", reason="Test"
    )


@pytest.mark.asyncio
async def test_notify_dispute_resolved_error(mock_branding) -> None:
    bot = AsyncMock(spec=Bot)
    bot.send_message.side_effect = TelegramAPIError(
        method=SendMessage(chat_id=1, text=""), message="Retry later"
    )
    await notification_service.notify_dispute_resolved(
        bot,
        maker_id=111,
        taker_id=222,
        order_id="uuid-123",
        decision="taker_wins",
        status="resolved",
    )


@pytest.mark.asyncio
async def test_notify_escrow_refunded_error(mock_branding) -> None:
    bot = AsyncMock(spec=Bot)
    bot.send_message.side_effect = TelegramAPIError(
        method=SendMessage(chat_id=1, text=""), message="Retry later"
    )
    res = await notification_service.notify_escrow_refunded(
        bot, maker_id=111, order_id="uuid-123", asset="USDT", amount=10.0
    )
    assert res is False


@pytest.mark.asyncio
async def test_notify_maker_order_activated_error(mock_branding) -> None:
    bot = AsyncMock(spec=Bot)
    bot.send_message.side_effect = TelegramAPIError(
        method=SendMessage(chat_id=1, text=""), message="Retry later"
    )
    res = await notification_service.notify_maker_order_activated(
        bot, maker_id=111, order_id="uuid-123", asset="USDT", amount=10.0
    )
    assert res is False


@pytest.mark.asyncio
async def test_notify_taker_order_activated_success(mock_branding) -> None:
    bot = AsyncMock(spec=Bot)
    res = await notification_service.notify_taker_order_activated(
        bot, taker_id=111, order_id="uuid-123", asset="USDT", amount=10.0
    )
    assert res is True
    bot.send_message.assert_called_once()


@pytest.mark.asyncio
async def test_notify_taker_order_activated_error(mock_branding) -> None:
    bot = AsyncMock(spec=Bot)
    bot.send_message.side_effect = TelegramAPIError(
        method=SendMessage(chat_id=1, text=""), message="Retry later"
    )
    res = await notification_service.notify_taker_order_activated(
        bot, taker_id=111, order_id="uuid-123", asset="USDT", amount=10.0
    )
    assert res is False


@pytest.mark.asyncio
async def test_notify_taker_escrow_released_with_tx_hash(mock_branding) -> None:
    bot = AsyncMock(spec=Bot)
    res = await notification_service.notify_taker_escrow_released(
        bot, taker_id=123, order_id="uuid-12345678", asset="USDT", amount=10.5, tx_hash="0xabcd"
    )
    assert res is True
    args, kwargs = bot.send_message.call_args
    assert "0xabcd" in args[1]
