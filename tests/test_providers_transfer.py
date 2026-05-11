"""Integration tests for Wallet Providers (Transfer & Fee Estimation)."""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from providers.wallet_provider import EvmWalletProvider, TonWalletProvider


@pytest.mark.asyncio
async def test_evm_provider_estimate_fee():
    provider = EvmWalletProvider(rpc_url="http://mock-rpc")

    # We need a mock that is awaitable when accessed as an attribute
    class AwaitableMock(AsyncMock):
        def __await__(self):
            return self().__await__()

    mock_w3 = MagicMock()
    mock_w3.eth.gas_price = AwaitableMock(return_value=20000000000)

    with patch("providers.wallet_provider.AsyncWeb3") as mock_w3_cls:
        mock_w3_cls.return_value = mock_w3
        mock_w3_cls.from_wei = MagicMock(return_value=Decimal("0.00042"))
        with patch("providers.wallet_provider.HAS_EVM", True):
            fee = await provider.estimate_fee("BNB")
            assert fee == Decimal("0.00042")


@pytest.mark.asyncio
async def test_evm_provider_transfer_native():
    provider = EvmWalletProvider(rpc_url="http://mock-rpc")
    private_key = "0" * 64

    class AwaitableMock(AsyncMock):
        def __await__(self):
            return self().__await__()

    mock_w3 = MagicMock()
    mock_w3.eth.get_transaction_count = AsyncMock(return_value=5)
    mock_w3.eth.chain_id = AwaitableMock(return_value=56)
    mock_w3.eth.gas_price = AwaitableMock(return_value=5000000000)
    mock_w3.eth.estimate_gas = AsyncMock(return_value=21000)

    mock_hash = MagicMock()
    mock_hash.hex.return_value = "0xhash"
    mock_w3.eth.send_raw_transaction = AsyncMock(return_value=mock_hash)
    mock_w3.eth.fee_history = AsyncMock(return_value={"baseFeePerGas": [1000000000]})

    mock_acc = MagicMock()
    mock_acc.address = "0xsender"
    mock_signed = MagicMock()
    mock_signed.raw_transaction = b"signed_data"
    mock_acc.sign_transaction.return_value = mock_signed

    with patch("providers.wallet_provider.AsyncWeb3") as mock_w3_cls:
        mock_w3_cls.return_value = mock_w3
        mock_w3_cls.to_checksum_address = MagicMock(side_effect=lambda x: x)
        mock_w3_cls.from_wei = MagicMock(side_effect=lambda v, u: Decimal(v) / Decimal(1e18))
        mock_w3_cls.to_wei = MagicMock(side_effect=lambda v, u: int(Decimal(v) * Decimal(1e18)))

        with (
            patch("providers.wallet_provider.Account.from_key", return_value=mock_acc),
            patch("providers.wallet_provider.HAS_EVM", True),
        ):
            tx_hash = await provider.transfer(private_key, "0xrecipient", "BNB", Decimal("1.0"))
            assert tx_hash == "0xhash"


@pytest.mark.asyncio
async def test_ton_provider_transfer_native():
    provider = TonWalletProvider(is_testnet=True)
    private_key = "0" * 64

    mock_client = AsyncMock()

    mock_wallet = MagicMock()
    mock_wallet.get_seqno = AsyncMock(return_value=10)
    mock_wallet.transfer = AsyncMock()

    mock_query = MagicMock()
    mock_query.message.hash.hex.return_value = "tonhash"
    mock_wallet.create_transfer_message.return_value = mock_query

    with patch("providers.wallet_provider.WalletV4R2") as mock_wallet_cls:
        mock_wallet_cls.from_private_key.return_value = mock_wallet
        with (
            patch.object(provider, "_get_client", return_value=mock_client),
            patch("providers.wallet_provider.HAS_TON", True),
        ):
            tx_hash = await provider.transfer(
                private_key, "UQrecipient", "TON", Decimal("10.0"), memo="test"
            )
            assert tx_hash == "tonhash"
            mock_wallet.transfer.assert_called_once()


@pytest.mark.asyncio
async def test_ton_provider_estimate_fee():
    provider = TonWalletProvider(is_testnet=True)
    fee = await provider.estimate_fee("TON")
    assert fee == Decimal("0.05")
