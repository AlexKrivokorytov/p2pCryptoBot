"""Unit tests for TONProvider."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from providers.ton import TONProvider


@pytest.mark.asyncio
async def test_ton_provider_get_client_mainnet():
    provider = TONProvider(is_testnet=False)
    with patch("pytoniq.LiteClient", new_callable=MagicMock) as mock_client_cls:
        mock_client_cls.from_mainnet_config = AsyncMock()
        client = await provider._get_client()
        mock_client_cls.from_mainnet_config.assert_called_once()
        assert client == mock_client_cls.from_mainnet_config.return_value


@pytest.mark.asyncio
async def test_ton_provider_get_client_testnet():
    provider = TONProvider(is_testnet=True)
    with patch("pytoniq.LiteClient", new_callable=MagicMock) as mock_client_cls:
        mock_client_cls.from_testnet_config = AsyncMock()
        client = await provider._get_client()
        mock_client_cls.from_testnet_config.assert_called_once()
        assert client == mock_client_cls.from_testnet_config.return_value


@pytest.mark.asyncio
async def test_ton_provider_connect_disconnect():
    provider = TONProvider()
    mock_client = AsyncMock()
    # Ensure provider._client is set so disconnect() can close it
    provider._client = mock_client
    with patch.object(provider, "_get_client", return_value=mock_client):
        await provider.connect()
        mock_client.connect.assert_called_once()

        await provider.disconnect()
        mock_client.close.assert_called_once()
        assert provider._client is None


@pytest.mark.asyncio
async def test_ton_provider_get_transactions():
    provider = TONProvider()
    mock_client = AsyncMock()

    # Mock complex pytoniq transaction structure
    tx = MagicMock()
    tx.hash = b"somehash"
    tx.utime = 12345
    tx.in_msg.info.type = "int_msg"
    tx.in_msg.info.value = 1000000000  # 1 TON

    # Mock memo parsing
    mock_body = MagicMock()
    tx.in_msg.body = mock_body
    mock_slice = MagicMock()
    mock_body.begin_parse.return_value = mock_slice
    mock_slice.__len__.return_value = 64
    mock_slice.load_uint.return_value = 0  # Comment prefix
    mock_slice.load_snake_string.return_value = "hello memo"

    mock_client.get_transactions.return_value = [tx]

    with patch.object(provider, "_get_client", return_value=mock_client):
        results = await provider.get_transactions("some_address")

        assert len(results) == 1
        assert results[0]["hash"] == b"somehash".hex()
        assert results[0]["memo"] == "hello memo"
        assert results[0]["amount_nanotons"] == 1000000000


@pytest.mark.asyncio
async def test_ton_provider_get_transactions_no_in_msg():
    provider = TONProvider()
    mock_client = AsyncMock()

    tx = MagicMock()
    tx.in_msg = None  # No message

    mock_client.get_transactions.return_value = [tx]

    with patch.object(provider, "_get_client", return_value=mock_client):
        results = await provider.get_transactions("some_address")
        assert len(results) == 0
