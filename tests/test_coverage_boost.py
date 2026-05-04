"""Additional tests to reach 95%+ coverage."""

from __future__ import annotations

import os
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.config import _LazySettings, _parse_admin_ids, _require
from db.models.wallet import UserWallet
from providers.crypto_pay import CryptoPayClient
from providers.wallet_provider import EvmWalletProvider, TonWalletProvider
from services import wallet_service


def test_config_require_error():
    """_require raises RuntimeError if env var is missing and no default."""
    # We use a unique key to ensure it's not set
    with pytest.raises(RuntimeError, match="Missing required environment"):
        _require("VERY_SPECIFIC_NON_EXISTENT_VAR_123")


def test_config_parse_admin_ids_empty():
    """_parse_admin_ids handles empty/invalid string."""
    assert _parse_admin_ids("") == frozenset()
    assert _parse_admin_ids("invalid") == frozenset()
    assert _parse_admin_ids("123, abc, 456") == frozenset([123, 456])


def test_config_lazy_settings_repr():
    """_LazySettings repr shows the settings string."""
    lazy = _LazySettings()
    # It will trigger get_settings() which returns a Settings object repr
    assert "Settings(" in repr(lazy)


@pytest.mark.asyncio
async def test_cryptopay_client_transfer_success():
    """CryptoPayClient.transfer returns dict on success."""
    with patch.dict(os.environ, {"CRYPTOPAY_TOKEN": "tok", "CRYPTOPAY_CALLBACK_SECRET": "sec"}):
        client = CryptoPayClient()
        with patch.object(client._api, "transfer", new_callable=AsyncMock) as mock_transfer:
            mock_transfer.return_value = MagicMock(status="completed", transfer_id=123)
            res = await client.transfer(123, "USDT", 10.5, "spend_uuid")
            assert res["transfer_id"] == 123
            assert res["status"] == "completed"


@pytest.mark.asyncio
async def test_cryptopay_client_get_exchange_rates():
    """CryptoPayClient.get_exchange_rates returns a list of rates."""
    with patch.dict(os.environ, {"CRYPTOPAY_TOKEN": "tok", "CRYPTOPAY_CALLBACK_SECRET": "sec"}):
        client = CryptoPayClient()
        with patch.object(client._api, "get_exchange_rates", new_callable=AsyncMock) as mock_rates:
            mock_rates.return_value = [
                MagicMock(source="USDT", target="USD", rate=1.0),
                MagicMock(source="TON", target="USD", rate=5.2),
            ]
            rates = await client.get_exchange_rates()
            assert rates[0]["source"] == "USDT"
            assert rates[1]["rate"] == 5.2


@pytest.mark.asyncio
async def test_cryptopay_client_close():
    """CryptoPayClient.close closes the inner api client."""
    with patch.dict(os.environ, {"CRYPTOPAY_TOKEN": "tok", "CRYPTOPAY_CALLBACK_SECRET": "sec"}):
        client = CryptoPayClient()
        with patch.object(client._api, "close", new_callable=AsyncMock) as mock_close:
            await client.close()
            mock_close.assert_called_once()


@pytest.mark.asyncio
async def test_wallet_service_get_provider_unsupported():
    """_get_provider raises ValueError for unknown chain."""
    with pytest.raises(ValueError, match="Unsupported chain"):
        wallet_service._get_provider("solana")


@pytest.mark.asyncio
async def test_wallet_service_get_provider_lazy_cache():
    """_get_provider caches the provider instance."""
    p1 = wallet_service._get_provider("evm")
    p2 = wallet_service._get_provider("evm")
    assert p1 is p2


@pytest.mark.asyncio
async def test_wallet_service_decrypt_key():
    """decrypt_wallet_key raises if decryption fails."""
    with patch("services.wallet_service.decrypt", side_effect=Exception("Decryption error")):
        wallet = UserWallet(encrypted_private_key="enc")
        with pytest.raises(Exception, match="Decryption error"):
            wallet_service.decrypt_wallet_key(wallet)


@pytest.mark.asyncio
async def test_evm_provider_transfer_stub():
    """EvmWalletProvider.transfer returns a stub hash."""
    provider = EvmWalletProvider(rpc_url="http://localhost")
    res = await provider.transfer("key", "to", "USDT", Decimal("10"))
    assert res.startswith("0x")
    assert len(res) == 66


@pytest.mark.asyncio
async def test_ton_provider_transfer_stub():
    """TonWalletProvider.transfer returns a stub hash."""
    provider = TonWalletProvider(endpoint="http://localhost")
    res = await provider.transfer("key", "to", "TON", Decimal("1"))
    assert len(res) == 64


@pytest.mark.asyncio
async def test_evm_provider_get_balance_unsupported():
    """Evm get_balance returns 0 for non-upper asset if logic fails."""
    provider = EvmWalletProvider(rpc_url="http://localhost")
    res = await provider.get_balance("0xaddr", "invalid")
    assert res == Decimal("0")


@pytest.mark.asyncio
async def test_evm_provider_get_balance_erc20():
    """Evm get_balance for ERC20 token."""
    provider = EvmWalletProvider(rpc_url="http://localhost")
    with patch("web3.AsyncWeb3") as mock_w3:
        w3 = mock_w3.return_value
        contract = MagicMock()
        w3.eth.contract.return_value = contract
        contract.functions.balanceOf.return_value.call = AsyncMock(return_value=10**18)
        contract.functions.decimals.return_value.call = AsyncMock(return_value=18)

        res = await provider.get_balance("0xaddr", "USDT")
        assert res == Decimal("1")


@pytest.mark.asyncio
async def test_ton_provider_generate_account():
    """Ton generate_account handles missing library gracefully."""
    with patch(
        "providers.wallet_provider._generate_ton_account", side_effect=ImportError("No pytoniq")
    ):
        provider = TonWalletProvider(endpoint="http://localhost")
        res = await provider.generate_wallet(123)
        assert res["address"].startswith("UQStub")


@pytest.mark.asyncio
async def test_ton_provider_get_balance_native():
    """Ton get_balance for native TON."""
    provider = TonWalletProvider(endpoint="http://localhost")
    with patch("aiohttp.ClientSession.get") as mock_get:
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value={"ok": True, "result": "2000000000"})
        mock_get.return_value.__aenter__.return_value = mock_resp

        res = await provider.get_balance("UQaddr", "TON")
        assert res == Decimal("2")
