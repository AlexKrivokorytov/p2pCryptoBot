"""Additional tests to reach 80%+ coverage."""

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


@pytest.mark.asyncio
async def test_wallet_service_get_provider_unsupported():
    """ValueError is raised for unsupported chain."""
    with pytest.raises(ValueError, match="Unsupported chain"):
        wallet_service._get_provider("solana")


@pytest.mark.asyncio
async def test_wallet_service_decrypt_key():
    """Decrypt wallet key returns plaintext."""
    # This requires a valid AES_KEY to be set in env (handled by conftest.py)
    from utils.encryption import encrypt

    enc_pk = encrypt("my_private_key")
    wallet = UserWallet(encrypted_private_key=enc_pk)

    decrypted = wallet_service.decrypt_wallet_key(wallet)
    assert decrypted == "my_private_key"


@pytest.mark.asyncio
async def test_cryptopay_client_unsupported_asset():
    """ValueError is raised for unsupported asset."""
    # We need env vars for CryptoPayClient init
    with patch.dict(os.environ, {"CRYPTOPAY_TOKEN": "test", "CRYPTOPAY_CALLBACK_SECRET": "test"}):
        client = CryptoPayClient()
        with pytest.raises(ValueError, match="Unsupported asset"):
            await client.create_invoice(asset="DOGE", amount=1.0, payload="test")

        with pytest.raises(ValueError, match="Unsupported asset"):
            await client.transfer(user_id=1, asset="DOGE", amount=1.0, spend_id="test")


@pytest.mark.asyncio
async def test_cryptopay_client_invalid_amount():
    """ValueError is raised for non-positive amount."""
    with patch.dict(os.environ, {"CRYPTOPAY_TOKEN": "test", "CRYPTOPAY_CALLBACK_SECRET": "test"}):
        client = CryptoPayClient()
        with pytest.raises(ValueError, match="Amount must be positive"):
            await client.create_invoice(asset="USDT", amount=0, payload="test")

        with pytest.raises(ValueError, match="Transfer amount must be positive"):
            await client.transfer(user_id=1, asset="USDT", amount=-1, spend_id="test")


@pytest.mark.asyncio
@patch("providers.crypto_pay.AioCryptoPay", new_callable=MagicMock)
async def test_cryptopay_client_transfer_success(mock_api_class):
    """Successful transfer returns expected dict."""
    mock_api = mock_api_class.return_value
    mock_api.transfer = AsyncMock()

    transfer_obj = MagicMock()
    transfer_obj.transfer_id = 12345
    transfer_obj.status = "completed"
    mock_api.transfer.return_value = transfer_obj

    with patch.dict(os.environ, {"CRYPTOPAY_TOKEN": "test", "CRYPTOPAY_CALLBACK_SECRET": "test"}):
        client = CryptoPayClient()
        res = await client.transfer(user_id=1, asset="USDT", amount=10.0, spend_id="sid")

        assert res["transfer_id"] == 12345
        assert res["status"] == "completed"
        mock_api.transfer.assert_called_once()


@pytest.mark.asyncio
@patch("providers.crypto_pay.AioCryptoPay", new_callable=MagicMock)
async def test_cryptopay_client_get_rates(mock_api_class):
    """Exchange rates are correctly mapped."""
    mock_api = mock_api_class.return_value
    mock_api.get_exchange_rates = AsyncMock()

    r1 = MagicMock(source="BTC", target="USD", rate="60000")
    mock_api.get_exchange_rates.return_value = [r1]

    with patch.dict(os.environ, {"CRYPTOPAY_TOKEN": "test", "CRYPTOPAY_CALLBACK_SECRET": "test"}):
        client = CryptoPayClient()
        rates = await client.get_exchange_rates()
        assert len(rates) == 1
        assert rates[0]["source"] == "BTC"
        assert rates[0]["rate"] == "60000"


@pytest.mark.asyncio
@patch("providers.crypto_pay.AioCryptoPay", new_callable=MagicMock)
async def test_cryptopay_client_close(mock_api_class):
    """Close calls api.close."""
    mock_api = mock_api_class.return_value
    mock_api.close = AsyncMock()

    with patch.dict(os.environ, {"CRYPTOPAY_TOKEN": "test", "CRYPTOPAY_CALLBACK_SECRET": "test"}):
        client = CryptoPayClient()
        await client.close()
        mock_api.close.assert_called_once()


@pytest.mark.asyncio
async def test_wallet_service_get_provider_lazy_cache():
    """Provider is cached after first access."""
    with patch("services.wallet_service.TonWalletProvider") as mock_ton:
        p1 = wallet_service._get_provider("ton")
        p2 = wallet_service._get_provider("ton")
        assert p1 is p2
        mock_ton.assert_called_once()


def test_config_require_error():
    """RuntimeError is raised when required env var is missing."""
    with (
        patch.dict(os.environ, clear=True),
        pytest.raises(RuntimeError, match="Missing required environment variable"),
    ):
        _require("NON_EXISTENT_VAR")


def test_config_parse_admin_ids_empty():
    """Empty string or None returns empty frozenset."""
    assert _parse_admin_ids("") == frozenset()


def test_config_lazy_settings_repr():
    """LazySettings repr works."""
    ls = _LazySettings()
    with patch("bot.config.get_settings") as mock_get:
        mock_get.return_value = "MockSettings"
        assert "MockSettings" in repr(ls)


@pytest.mark.asyncio
async def test_evm_provider_transfer_stub():
    """Evm provider transfer returns a hex hash."""
    provider = EvmWalletProvider(rpc_url="http://localhost")
    res = await provider.transfer("pk", "0xaddr", "USDT", Decimal("1.0"))
    assert res.startswith("0x")
    assert len(res) == 66


@pytest.mark.asyncio
async def test_ton_provider_transfer_stub():
    """Ton provider transfer returns a hex hash."""
    provider = TonWalletProvider(endpoint="http://localhost")
    res = await provider.transfer("pk", "UQaddr", "TON", Decimal("1.0"))
    assert len(res) == 64


@pytest.mark.asyncio
async def test_evm_provider_get_balance_unsupported():
    """Evm get_balance returns 0 for unsupported assets."""
    provider = EvmWalletProvider(rpc_url="http://localhost")
    res = await provider.get_balance("0xaddr", "DOGE")
    assert res == Decimal("0")


@pytest.mark.asyncio
async def test_evm_provider_get_balance_error():
    """Evm get_balance returns 0 on exception."""
    provider = EvmWalletProvider(rpc_url="http://localhost")
    with patch("web3.AsyncWeb3", side_effect=Exception("RPC Down")):
        res = await provider.get_balance("0xaddr", "ETH")
        assert res == Decimal("0")
