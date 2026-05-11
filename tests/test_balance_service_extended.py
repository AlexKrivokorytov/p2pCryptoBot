"""Extended tests for balance_service."""

import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from db.models.wallet import UserWallet
from services import balance_service


@pytest.mark.asyncio
async def test_balance_service_unsupported_chain(session):
    # Wallet with a chain not in _CHAIN_ASSETS
    wallet = UserWallet(chain="unsupported", address="addr", user_id=1)

    with patch("services.wallet_service.get_user_wallets", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = [wallet]

        results = await balance_service.get_portfolio_balances(session, 1)
        assert len(results) == 1
        assert results[0].balances == {}


@pytest.mark.asyncio
async def test_fetch_single_balance_timeout():
    wallet = UserWallet(chain="ton", address="addr")

    with patch("services.balance_service._get_provider") as mock_provider:
        # Mock provider.get_balance to hang
        mock_provider.return_value.get_balance = AsyncMock(side_effect=asyncio.TimeoutError)

        # We need to reduce timeout for test speed
        with patch("services.balance_service._BALANCE_TIMEOUT_SEC", 0.01):
            asset, balance = await balance_service._fetch_single_balance(wallet, "TON")
            assert balance == Decimal("0")
