"""Tests for exchange broker providers."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from providers.broker.binance import BinanceBroker
from providers.broker.bybit import BybitBroker
from providers.broker.okx import OKXBroker


@pytest.mark.asyncio
async def test_binance_broker():
    with patch("ccxt.async_support.binance") as mock_ccxt:
        client = mock_ccxt.return_value
        client.fetch_balance = AsyncMock(return_value={"free": {"USDT": 100.5}})
        client.create_market_order = AsyncMock(return_value={"id": "order_123"})
        client.close = AsyncMock()

        broker = BinanceBroker()
        bal = await broker.fetch_balance("USDT")
        assert bal == 100.5

        order = await broker.create_order("USDT", "USD", "buy", 10.0)
        assert order["id"] == "order_123"

        await broker.close()
        client.close.assert_called_once()


@pytest.mark.asyncio
async def test_bybit_broker():
    with patch("ccxt.async_support.bybit") as mock_ccxt:
        client = mock_ccxt.return_value
        client.fetch_balance = AsyncMock(return_value={"free": {"USDT": 50.0}})
        client.create_market_order = AsyncMock(return_value={"id": "bybit_123"})
        client.close = AsyncMock()

        broker = BybitBroker()
        bal = await broker.fetch_balance("USDT")
        assert bal == 50.0

        order = await broker.create_order("USDT", "USD", "sell", 5.0)
        assert order["id"] == "bybit_123"

        await broker.close()


@pytest.mark.asyncio
async def test_okx_broker():
    with patch("ccxt.async_support.okx") as mock_ccxt:
        client = mock_ccxt.return_value
        client.fetch_balance = AsyncMock(return_value={"free": {"USDT": 75.0}})
        client.create_market_order = AsyncMock(return_value={"id": "okx_123"})
        client.close = AsyncMock()

        broker = OKXBroker()
        bal = await broker.fetch_balance("USDT")
        assert bal == 75.0

        order = await broker.create_order("USDT", "USD", "buy", 1.0)
        assert order["id"] == "okx_123"

        await broker.close()
