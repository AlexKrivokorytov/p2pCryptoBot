"""Extended tests for start handler — covers line 24 (tg_user is None guard)
and order handler lines 49-51, 70, 152-158."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from bot.handlers import order as order_handlers
from bot.handlers import start as start_handlers

pytestmark = pytest.mark.unit

# ── start.py line 24: tg_user is None guard ───────────────────────────────────


@pytest.mark.asyncio
async def test_cmd_start_no_from_user() -> None:
    """cmd_start returns early and does nothing when message.from_user is None."""
    message = AsyncMock()
    message.from_user = None  # ← triggers line 24 guard
    session = AsyncMock()

    await start_handlers.cmd_start(message, session)

    # Must not attempt to answer or touch DB
    message.answer.assert_not_called()
    session.begin.assert_not_called()


# ── order.py lines 49-51: unknown asset in cb_asset_chosen ───────────────────


@pytest.mark.asyncio
async def test_cb_asset_chosen_invalid_asset() -> None:
    """cb_asset_chosen sends alert for an unsupported asset ticker."""
    callback = AsyncMock()
    callback.data = "asset:FAKECOIN"
    state = AsyncMock()

    await order_handlers.cb_asset_chosen(callback, state)

    # Should alert and return — NOT set FSM state
    callback.answer.assert_called_once()
    assert "Unknown asset" in callback.answer.call_args[0][0]
    state.set_state.assert_not_called()


# ── order.py line 70: zero amount in msg_amount ──────────────────────────────


@pytest.mark.asyncio
async def test_msg_amount_zero_value() -> None:
    """msg_amount rejects zero as an invalid amount."""
    message = AsyncMock()
    message.text = "0"
    state = AsyncMock()

    await order_handlers.msg_amount(message, state)

    # Should answer with error, not advance FSM
    message.answer.assert_called_once()
    assert "valid positive" in message.answer.call_args[0][0]
    state.set_state.assert_not_called()


@pytest.mark.asyncio
async def test_msg_amount_non_numeric() -> None:
    """msg_amount rejects non-numeric input."""
    message = AsyncMock()
    message.text = "abc"
    state = AsyncMock()

    await order_handlers.msg_amount(message, state)

    message.answer.assert_called_once()
    state.set_state.assert_not_called()


# ── order.py: ad creation failure in cb_ad_confirmed ─────────────────────────


@pytest.mark.asyncio
@patch("bot.handlers.order.order_service.create_order", new_callable=AsyncMock)
async def test_cb_ad_confirmed_service_error(mock_create: AsyncMock) -> None:
    """cb_ad_confirmed shows error message when order_service raises."""
    mock_create.side_effect = ValueError("Unsupported asset")

    callback = AsyncMock()
    callback.from_user.id = 123
    callback.data = "ad:confirmed"

    state = AsyncMock()
    state.get_data = AsyncMock(
        return_value={
            "order_type": "sell_crypto",
            "asset": "USDT",
            "amount": 100.0,
            "fiat_currency": "USD",
            "fiat_amount": 90.0,
            "payment_method": "Sberbank",
        }
    )

    session = AsyncMock()
    crypto_pay = AsyncMock()

    await order_handlers.cb_ad_confirmed(callback, state, session, crypto_pay)

    # Must show error and call answer()
    callback.message.edit_text.assert_called_once()
    error_text = callback.message.edit_text.call_args[0][0]
    assert "Unsupported asset" in error_text
    callback.answer.assert_called_once()
