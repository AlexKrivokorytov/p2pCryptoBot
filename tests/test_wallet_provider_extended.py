"""Extended tests for Wallet Providers."""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from providers.wallet_provider import EvmWalletProvider, TonWalletProvider


@pytest.mark.asyncio
async def test_evm_balance_unsupported_asset():
    provider = EvmWalletProvider(rpc_url="http://localhost")
    with patch("web3.AsyncWeb3", spec=True):
        balance = await provider.get_balance("0x123", "UNKNOWN")
        assert balance == Decimal("0")


@pytest.mark.asyncio
async def test_evm_balance_rpc_error():
    provider = EvmWalletProvider(rpc_url="http://localhost")
    with patch("providers.wallet_provider.AsyncWeb3") as mock_w3_cls:
        mock_w3_cls.return_value.eth.get_balance.side_effect = Exception("RPC Fail")
        mock_w3_cls.to_checksum_address = MagicMock(side_effect=lambda x: x)
        balance = await provider.get_balance("0x123", "BNB")
        assert balance == Decimal("0")


@pytest.mark.asyncio
async def test_evm_balance_erc20():
    provider = EvmWalletProvider(rpc_url="http://localhost")
    with patch("providers.wallet_provider.AsyncWeb3") as mock_w3_cls:
        mock_w3 = mock_w3_cls.return_value
        mock_contract = MagicMock()
        mock_w3.eth.contract.return_value = mock_contract
        mock_w3_cls.to_checksum_address = MagicMock(side_effect=lambda x: x)
        # Mocking the async call .call()
        mock_contract.functions.balanceOf.return_value.call = AsyncMock(return_value=10 * 10**18)

        balance = await provider.get_balance("0x123", "USDT")
        assert balance == Decimal("10")


@pytest.mark.asyncio
async def test_ton_balance_unsupported_asset():
    provider = TonWalletProvider(endpoint="http://localhost")
    balance = await provider.get_balance("UQ_ADDR", "ETH")
    assert balance == Decimal("0")


@pytest.mark.asyncio
async def test_ton_balance_http_error():
    provider = TonWalletProvider(endpoint="http://localhost")
    with patch("aiohttp.ClientSession") as mock_session_cls:
        mock_resp = AsyncMock()
        mock_resp.status = 500
        mock_get = mock_session_cls.return_value.__aenter__.return_value.get
        mock_get.return_value.__aenter__.return_value = mock_resp

        balance = await provider.get_balance("UQ_ADDR", "TON")
        assert balance == Decimal("0")


@pytest.mark.asyncio
async def test_ton_balance_exception():
    provider = TonWalletProvider(endpoint="http://localhost")
    with patch("aiohttp.ClientSession", side_effect=Exception("Network down")):
        balance = await provider.get_balance("UQ_ADDR", "TON")
        assert balance == Decimal("0")
