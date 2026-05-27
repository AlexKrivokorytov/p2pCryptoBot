"""Tests for services/marketplace_notifications.py — push notification functions."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from services.marketplace_notifications import (
    _safe_send,
    notify_deal_cancelled,
    notify_deal_completed,
    notify_deal_created,
    notify_deal_delivered,
    notify_deal_paid,
    notify_dispute_opened,
    notify_dispute_resolved,
    notify_new_message,
    notify_seller_payout_sent,
    notify_stars_purchase,
)

pytestmark = pytest.mark.unit

DEAL_ID = "abc12345-0000-0000-0000-000000000000"


def _make_bot() -> AsyncMock:
    """Return a mocked Bot that succeeds by default."""
    bot = AsyncMock(spec=Bot)
    bot.send_message = AsyncMock(return_value=MagicMock())
    return bot


def _make_deal(
    seller_id: int = 100,
    buyer_id: int = 200,
) -> MagicMock:
    deal = MagicMock()
    deal.id = DEAL_ID
    deal.seller_id = seller_id
    deal.buyer_id = buyer_id
    deal.amount = 99.0
    deal.currency_type = "XTR"
    deal.product = MagicMock()
    deal.product.title = "Test Product"
    deal.product.crypto_asset = "USDT"
    deal.tx_hash_release = "0xdeadbeef1234"
    return deal


# ── _safe_send ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_safe_send_success() -> None:
    """_safe_send returns True on successful Telegram delivery."""
    bot = _make_bot()
    result = await _safe_send(bot, 123, "Hello", event="test_event")
    assert result is True
    bot.send_message.assert_called_once()


@pytest.mark.asyncio
async def test_safe_send_telegram_error_returns_false() -> None:
    """_safe_send returns False (never raises) on TelegramAPIError."""
    bot = _make_bot()
    bot.send_message.side_effect = TelegramAPIError(method=MagicMock(), message="blocked")

    result = await _safe_send(bot, 123, "Hello", event="test_event")

    assert result is False


@pytest.mark.asyncio
async def test_safe_send_with_reply_markup() -> None:
    """_safe_send forwards reply_markup to bot.send_message."""
    bot = _make_bot()
    keyboard = MagicMock()

    await _safe_send(bot, 456, "msg", event="ev", reply_markup=keyboard)

    call_kwargs = bot.send_message.call_args[1]
    assert call_kwargs.get("reply_markup") == keyboard


# ── notify_deal_created ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_notify_deal_created_sends_to_seller() -> None:
    """notify_deal_created sends message to the seller."""
    bot = _make_bot()

    with patch(
        "services.marketplace_notifications._save_inapp_notification", new_callable=AsyncMock
    ):
        result = await notify_deal_created(
            bot=bot,
            seller_id=100,
            buyer_first_name="Alice",
            deal_id=DEAL_ID,
            product_title="My Product",
            amount=50.0,
            currency="XTR",
        )

    assert result is True
    assert bot.send_message.call_args[0][0] == 100


@pytest.mark.asyncio
async def test_notify_deal_created_telegram_error_returns_false() -> None:
    """notify_deal_created returns False on Telegram error."""
    bot = _make_bot()
    bot.send_message.side_effect = TelegramAPIError(method=MagicMock(), message="error")

    with patch(
        "services.marketplace_notifications._save_inapp_notification", new_callable=AsyncMock
    ):
        result = await notify_deal_created(
            bot=bot,
            seller_id=100,
            buyer_first_name="Alice",
            deal_id=DEAL_ID,
            product_title="Product",
            amount=50.0,
            currency="XTR",
        )

    assert result is False


# ── notify_deal_paid ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_notify_deal_paid_sends_to_seller() -> None:
    """notify_deal_paid sends message to seller_id."""
    bot = _make_bot()

    with patch(
        "services.marketplace_notifications._save_inapp_notification", new_callable=AsyncMock
    ):
        result = await notify_deal_paid(
            bot=bot,
            seller_id=100,
            deal_id=DEAL_ID,
            product_title="Product",
            amount=99.0,
            currency="XTR",
        )

    assert result is True
    assert bot.send_message.call_args[0][0] == 100


# ── notify_deal_delivered ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_notify_deal_delivered_sends_to_buyer() -> None:
    """notify_deal_delivered sends message to buyer_id."""
    bot = _make_bot()

    with patch(
        "services.marketplace_notifications._save_inapp_notification", new_callable=AsyncMock
    ):
        result = await notify_deal_delivered(
            bot=bot,
            buyer_id=200,
            deal_id=DEAL_ID,
            product_title="Product",
        )

    assert result is True
    assert bot.send_message.call_args[0][0] == 200


# ── notify_deal_completed ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_notify_deal_completed_sends_to_seller() -> None:
    """notify_deal_completed sends message to seller."""
    bot = _make_bot()

    result = await notify_deal_completed(
        bot=bot,
        seller_id=100,
        deal_id=DEAL_ID,
        product_title="Product",
    )

    assert result is True
    assert bot.send_message.call_args[0][0] == 100


# ── notify_stars_purchase ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_notify_stars_purchase_sends_to_seller() -> None:
    """notify_stars_purchase sends to seller_id with star count info."""
    bot = _make_bot()

    result = await notify_stars_purchase(
        bot=bot,
        seller_id=100,
        buyer_first_name="Bob",
        deal_id=DEAL_ID,
        product_title="Product",
        stars=100,
    )

    assert result is True
    assert bot.send_message.call_args[0][0] == 100


# ── notify_deal_cancelled ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_notify_deal_cancelled_sends_to_both_parties() -> None:
    """notify_deal_cancelled notifies both seller and buyer."""
    bot = _make_bot()

    await notify_deal_cancelled(
        bot=bot,
        seller_id=100,
        buyer_id=200,
        deal_id=DEAL_ID,
        product_title="Product",
    )

    assert bot.send_message.call_count == 2
    recipients = {call[0][0] for call in bot.send_message.call_args_list}
    assert 100 in recipients
    assert 200 in recipients


@pytest.mark.asyncio
async def test_notify_deal_cancelled_telegram_error_does_not_raise() -> None:
    """notify_deal_cancelled swallows TelegramAPIError gracefully."""
    bot = _make_bot()
    bot.send_message.side_effect = TelegramAPIError(method=MagicMock(), message="blocked")

    # Must not raise
    await notify_deal_cancelled(
        bot=bot,
        seller_id=100,
        buyer_id=200,
        deal_id=DEAL_ID,
        product_title="Product",
    )


# ── notify_new_message ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_notify_new_message_sends_to_recipient() -> None:
    """notify_new_message sends a chat message notification."""
    bot = _make_bot()

    result = await notify_new_message(
        bot=bot,
        recipient_id=300,
        sender_name="Charlie",
        deal_id=DEAL_ID,
        product_title="Product",
    )

    assert result is True
    assert bot.send_message.call_args[0][0] == 300


# ── notify_dispute_opened ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_notify_dispute_opened_notifies_both_parties() -> None:
    """notify_dispute_opened sends to buyer and seller."""
    bot = _make_bot()

    await notify_dispute_opened(
        bot=bot,
        buyer_id=200,
        seller_id=100,
        deal_id=DEAL_ID,
        reason="Item not received",
    )

    assert bot.send_message.call_count == 2
    recipients = {call[0][0] for call in bot.send_message.call_args_list}
    assert 100 in recipients
    assert 200 in recipients


@pytest.mark.asyncio
async def test_notify_dispute_opened_telegram_error_does_not_raise() -> None:
    """notify_dispute_opened swallows Telegram errors gracefully."""
    bot = _make_bot()
    bot.send_message.side_effect = TelegramAPIError(method=MagicMock(), message="blocked")

    await notify_dispute_opened(
        bot=bot,
        buyer_id=200,
        seller_id=100,
        deal_id=DEAL_ID,
        reason="Test reason",
    )


# ── notify_dispute_resolved ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_notify_dispute_resolved_seller_wins() -> None:
    """notify_dispute_resolved notifies both parties when seller wins."""
    bot = _make_bot()

    await notify_dispute_resolved(
        bot=bot,
        buyer_id=200,
        seller_id=100,
        deal_id=DEAL_ID,
        resolution="seller",
        comment="Evidence supports seller",
    )

    assert bot.send_message.call_count == 2
    # Both get the same message about resolution
    for call in bot.send_message.call_args_list:
        assert "seller" in call[0][1].lower() or "released" in call[0][1].lower()


@pytest.mark.asyncio
async def test_notify_dispute_resolved_buyer_wins() -> None:
    """notify_dispute_resolved notifies both parties when buyer wins."""
    bot = _make_bot()

    await notify_dispute_resolved(
        bot=bot,
        buyer_id=200,
        seller_id=100,
        deal_id=DEAL_ID,
        resolution="buyer",
    )

    assert bot.send_message.call_count == 2


# ── notify_seller_payout_sent ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_notify_seller_payout_sent_success() -> None:
    """notify_seller_payout_sent sends message to seller with tx hash."""
    bot = _make_bot()
    deal = _make_deal()

    with patch(
        "services.marketplace_notifications._save_inapp_notification", new_callable=AsyncMock
    ):
        result = await notify_seller_payout_sent(bot=bot, deal=deal)

    assert result is True
    assert bot.send_message.call_args[0][0] == deal.seller_id


@pytest.mark.asyncio
async def test_notify_seller_payout_sent_no_tx_hash() -> None:
    """notify_seller_payout_sent handles missing tx_hash gracefully."""
    bot = _make_bot()
    deal = _make_deal()
    deal.tx_hash_release = None

    with patch(
        "services.marketplace_notifications._save_inapp_notification", new_callable=AsyncMock
    ):
        result = await notify_seller_payout_sent(bot=bot, deal=deal)

    assert result is True
