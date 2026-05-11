"""Tests for providers/wallet_provider.py — EvmWalletProvider and TonWalletProvider edge cases."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from providers.wallet_provider import EvmWalletProvider, TonWalletProvider

# ── EvmWalletProvider ─────────────────────────────────────────────────────────


class TestEvmWalletProviderGetBalance:
    """Tests for EvmWalletProvider.get_balance() uncovered branches."""

    @pytest.fixture
    def provider(self) -> EvmWalletProvider:
        return EvmWalletProvider(rpc_url="https://fake-rpc.example.com")

    @pytest.mark.asyncio
    async def test_get_balance_native_eth(self, provider: EvmWalletProvider) -> None:
        """Should return ETH balance in ether for native asset."""
        mock_w3 = MagicMock()
        mock_w3.eth.get_balance = AsyncMock(return_value=1_000_000_000_000_000_000)

        with patch("providers.wallet_provider.AsyncWeb3") as mock_aw3_cls:
            mock_aw3_cls.return_value = mock_w3
            mock_aw3_cls.from_wei = MagicMock(return_value="1.0")
            mock_aw3_cls.to_checksum_address = MagicMock(side_effect=lambda x: x)

            balance = await provider.get_balance("0xDeadBeef", "ETH")

        assert balance == Decimal("1.0")

    @pytest.mark.asyncio
    async def test_get_balance_unsupported_asset_returns_zero(
        self, provider: EvmWalletProvider
    ) -> None:
        """Unsupported asset should return Decimal('0') without error."""
        with patch("providers.wallet_provider.AsyncWeb3"):
            balance = await provider.get_balance("0xDeadBeef", "UNKNOWN_TOKEN")
        assert balance == Decimal("0")

    @pytest.mark.asyncio
    async def test_get_balance_erc20(self, provider: EvmWalletProvider) -> None:
        """Should fetch ERC20 balance using contract call."""
        mock_w3 = MagicMock()
        mock_contract = MagicMock()
        mock_w3.eth.contract.return_value = mock_contract
        # Mock the async call: contract.functions.balanceOf(addr).call()
        mock_contract.functions.balanceOf.return_value.call = AsyncMock(return_value=10 * 10**18)

        with patch("providers.wallet_provider.AsyncWeb3") as mock_aw3_cls:
            mock_aw3_cls.return_value = mock_w3
            mock_aw3_cls.to_checksum_address = MagicMock(side_effect=lambda x: x)

            balance = await provider.get_balance("0x123", "USDT")

        assert balance == Decimal("10")

    @pytest.mark.asyncio
    async def test_get_balance_rpc_error_returns_zero(self, provider: EvmWalletProvider) -> None:
        """Should return zero if RPC call raises an exception."""
        mock_w3 = MagicMock()
        mock_w3.eth.get_balance = AsyncMock(side_effect=Exception("RPC Error"))

        with patch("providers.wallet_provider.AsyncWeb3") as mock_aw3_cls:
            mock_aw3_cls.return_value = mock_w3
            mock_aw3_cls.to_checksum_address = MagicMock(side_effect=lambda x: x)

            balance = await provider.get_balance("0x123", "ETH")

        assert balance == Decimal("0")


# ── TonWalletProvider ─────────────────────────────────────────────────────────


class TestTonWalletProviderGetBalance:
    """Tests for TonWalletProvider.get_balance() uncovered branches."""

    @pytest.fixture
    def provider(self) -> TonWalletProvider:
        # Patch HAS_TON before creating provider
        with patch("providers.wallet_provider.HAS_TON", True):
            return TonWalletProvider(is_testnet=True)

    @pytest.mark.asyncio
    async def test_get_balance_non_ton_asset_returns_zero(
        self, provider: TonWalletProvider
    ) -> None:
        """Non-TON assets should immediately return Decimal('0')."""
        balance = await provider.get_balance("UQfakeaddress", "USDT")
        assert balance == Decimal("0")

    @pytest.mark.asyncio
    async def test_get_balance_ton_success(self, provider: TonWalletProvider) -> None:
        """Successful TON balance fetch should return correct Decimal value."""
        mock_client = AsyncMock()
        mock_acc = MagicMock()
        mock_acc.balance = 5_000_000_000
        mock_client.get_account_state.return_value = mock_acc

        with (
            patch("providers.wallet_provider.HAS_TON", True),
            patch.object(provider, "_get_client", return_value=mock_client),
        ):
            balance = await provider.get_balance("UQfakeaddress", "TON")

        assert balance == Decimal("5")

    @pytest.mark.asyncio
    async def test_get_balance_ton_exception_returns_zero(
        self, provider: TonWalletProvider
    ) -> None:
        """Exception during call should be caught and return Decimal('0')."""
        with (
            patch("providers.wallet_provider.HAS_TON", True),
            patch.object(provider, "_get_client", side_effect=Exception("Connection failed")),
        ):
            balance = await provider.get_balance("UQfakeaddress", "TON")

        assert balance == Decimal("0")


class TestTonWalletProviderTransfer:
    """Tests for TonWalletProvider.transfer() implementation."""

    @pytest.mark.asyncio
    async def test_transfer_returns_hash(self) -> None:
        """transfer() should return a transaction hash."""
        with patch("providers.wallet_provider.HAS_TON", True):
            provider = TonWalletProvider(is_testnet=True)

        mock_client = AsyncMock()
        mock_wallet = MagicMock()
        mock_wallet.get_seqno = AsyncMock(return_value=1)
        mock_wallet.transfer = AsyncMock()

        mock_query = MagicMock()
        mock_query.message.hash.hex.return_value = "tonhash"
        mock_wallet.create_transfer_message.return_value = mock_query

        with (
            patch("providers.wallet_provider.HAS_TON", True),
            patch("providers.wallet_provider.WalletV4R2") as mock_w_cls,
            patch.object(provider, "_get_client", return_value=mock_client),
        ):
            mock_w_cls.from_private_key.return_value = mock_wallet

            result = await provider.transfer(
                private_key="0" * 64,
                to_address="UQdestination",
                asset="TON",
                amount=Decimal("1.5"),
            )

        assert result == "tonhash"
