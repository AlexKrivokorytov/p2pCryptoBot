"""Tests for telegram handlers (ad creation + order book browsing)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from aiogram.fsm.context import FSMContext

from bot.handlers import order as order_handlers
from bot.states import CreateAdFSM

# ═══════════════════════════════════════════════════════════════════════════════
# CREATE AD FLOW
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_cb_ad_create() -> None:
    """Test start ad creation callback."""
    callback = AsyncMock()
    state = AsyncMock(spec=FSMContext)

    await order_handlers.cb_ad_create(callback, state)

    state.set_state.assert_called_once_with(CreateAdFSM.choose_type)
    callback.message.edit_text.assert_called_once()
    assert "Create Ad" in callback.message.edit_text.call_args[0][0]


@pytest.mark.asyncio
async def test_cb_ad_type_chosen() -> None:
    """Test callback query for ad type selection."""
    callback = AsyncMock()
    callback.data = "adtype:sell_crypto"
    state = AsyncMock(spec=FSMContext)

    await order_handlers.cb_ad_type_chosen(callback, state)

    state.update_data.assert_called_once_with(order_type="sell_crypto")
    state.set_state.assert_called_once_with(CreateAdFSM.choose_asset)
    callback.message.edit_text.assert_called_once()
    assert "sell crypto" in callback.message.edit_text.call_args[0][0]


@pytest.mark.asyncio
async def test_cb_asset_chosen() -> None:
    """Test callback query for asset selection."""
    callback = AsyncMock()
    callback.data = "asset:BTC"
    state = AsyncMock(spec=FSMContext)

    await order_handlers.cb_asset_chosen(callback, state)

    state.update_data.assert_called_once_with(asset="BTC")
    state.set_state.assert_called_once_with(CreateAdFSM.enter_amount)
    callback.message.edit_text.assert_called_once()
    assert "crypto amount" in callback.message.edit_text.call_args[0][0]


@pytest.mark.asyncio
async def test_msg_amount_valid() -> None:
    """Test entering a valid amount."""
    message = AsyncMock()
    message.text = "1.5"
    state = AsyncMock(spec=FSMContext)

    await order_handlers.msg_amount(message, state)

    state.update_data.assert_called_once_with(amount=1.5)
    state.set_state.assert_called_once_with(CreateAdFSM.enter_fiat_currency)
    message.answer.assert_called_once()
    assert "fiat currency" in message.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_msg_amount_invalid() -> None:
    """Test entering an invalid amount."""
    message = AsyncMock()
    message.text = "not_a_number"
    state = AsyncMock(spec=FSMContext)

    await order_handlers.msg_amount(message, state)

    state.update_data.assert_not_called()
    message.answer.assert_called_once()
    assert "valid positive number" in message.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_msg_fiat_currency_valid() -> None:
    """Test entering a valid fiat currency."""
    message = AsyncMock()
    message.text = "eur"
    state = AsyncMock(spec=FSMContext)

    await order_handlers.msg_fiat_currency(message, state)

    state.update_data.assert_called_once_with(fiat_currency="EUR")
    state.set_state.assert_called_once_with(CreateAdFSM.enter_fiat_amount)
    message.answer.assert_called_once()
    assert "fiat amount" in message.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_msg_fiat_currency_invalid() -> None:
    """Test entering an invalid fiat currency."""
    message = AsyncMock()
    message.text = "123"
    state = AsyncMock(spec=FSMContext)

    await order_handlers.msg_fiat_currency(message, state)

    state.update_data.assert_not_called()
    message.answer.assert_called_once()
    assert "Invalid currency code" in message.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_msg_fiat_amount_valid() -> None:
    """Test entering a valid fiat amount prompts payment method selection."""
    message = AsyncMock()
    message.text = "100.5"
    state = AsyncMock(spec=FSMContext)

    await order_handlers.msg_fiat_amount(message, state)

    state.update_data.assert_called_once_with(fiat_amount=100.5)
    state.set_state.assert_called_once_with(CreateAdFSM.enter_payment_method)
    message.answer.assert_called_once()
    assert "payment method" in message.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_msg_fiat_amount_invalid() -> None:
    """Test entering an invalid fiat amount."""
    message = AsyncMock()
    message.text = "-10"
    state = AsyncMock(spec=FSMContext)

    await order_handlers.msg_fiat_amount(message, state)

    state.update_data.assert_not_called()
    message.answer.assert_called_once()
    assert "valid positive fiat amount" in message.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_cb_payment_method() -> None:
    """Test payment method selection shows summary."""
    callback = AsyncMock()
    callback.data = "paymethod:Sberbank"
    state = AsyncMock(spec=FSMContext)
    state.get_data.return_value = {
        "order_type": "sell_crypto",
        "asset": "USDT",
        "amount": 10.0,
        "fiat_currency": "USD",
        "fiat_amount": 100.0,
    }

    await order_handlers.cb_payment_method(callback, state)

    state.update_data.assert_called_once_with(payment_method="Sberbank")
    state.set_state.assert_called_once_with(CreateAdFSM.confirm)
    callback.message.edit_text.assert_called_once()
    assert "Ad Summary" in callback.message.edit_text.call_args[0][0]


@pytest.mark.asyncio
async def test_cb_ad_confirmed_success() -> None:
    """Test successful ad confirmation."""
    callback = AsyncMock()
    callback.from_user.id = 123
    state = AsyncMock(spec=FSMContext)
    state.get_data.return_value = {
        "order_type": "sell_crypto",
        "asset": "USDT",
        "amount": 10.0,
        "fiat_currency": "USD",
        "fiat_amount": 100.0,
        "payment_method": "Sberbank",
    }
    session = AsyncMock()
    crypto_pay = AsyncMock()

    with patch(
        "bot.handlers.order.order_service.create_order", new_callable=AsyncMock
    ) as mock_create:
        mock_create.return_value = {"order_id": "uuid-123", "payment_url": "http://pay.me"}
        await order_handlers.cb_ad_confirmed(callback, state, session, crypto_pay)

        mock_create.assert_called_once()
        state.clear.assert_called_once()
        callback.message.edit_text.assert_called_once()
        assert "Ad created" in callback.message.edit_text.call_args[0][0]


@pytest.mark.asyncio
async def test_cb_cancel_ad() -> None:
    """Test ad creation cancellation."""
    callback = AsyncMock()
    state = AsyncMock(spec=FSMContext)

    await order_handlers.cb_cancel_ad(callback, state)

    state.clear.assert_called_once()
    callback.message.edit_text.assert_called_once()
    assert "cancelled" in callback.message.edit_text.call_args[0][0]


# ═══════════════════════════════════════════════════════════════════════════════
# ORDER BOOK BROWSING
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_cb_market_browse() -> None:
    """Test market browse callback fetches active orders."""
    callback = AsyncMock()
    state = AsyncMock(spec=FSMContext)
    session = AsyncMock()

    with patch(
        "bot.handlers.order.order_service.get_active_orders", new_callable=AsyncMock
    ) as mock_get:
        mock_get.return_value = {
            "orders": [],
            "page": 1,
            "total_pages": 1,
            "total_count": 0,
        }
        await order_handlers.cb_market_browse(callback, session, state)

        mock_get.assert_called_once_with(session, page=1)
        callback.message.edit_text.assert_called_once()
        assert "P2P Market" in callback.message.edit_text.call_args[0][0]
