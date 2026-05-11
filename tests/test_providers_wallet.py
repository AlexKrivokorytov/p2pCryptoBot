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
    async def test_get_balance_exception_returns_zero(self, provider: EvmWalletProvider) -> None:
        """Exception during RPC call should be caught and return Decimal('0')."""
        with patch("providers.wallet_provider.AsyncWeb3", side_effect=Exception("RPC failed")):
            balance = await provider.get_balance("0xDeadBeef", "ETH")
        assert balance == Decimal("0")


# ── TonWalletProvider ─────────────────────────────────────────────────────────


class TestTonWalletProviderGetBalance:
    """Tests for TonWalletProvider.get_balance() uncovered branches."""

    @pytest.fixture
    def provider(self) -> TonWalletProvider:
        return TonWalletProvider(endpoint="https://fake-toncenter.com/jsonRPC")

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
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value={"ok": True, "result": "5000000000"})

        mock_get_cm = MagicMock()
        mock_get_cm.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_get_cm.__aexit__ = AsyncMock(return_value=None)

        mock_http = MagicMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=None)
        mock_http.get = MagicMock(return_value=mock_get_cm)

        with patch("providers.wallet_provider.aiohttp.ClientSession", return_value=mock_http):
            balance = await provider.get_balance("UQfakeaddress", "TON")

        # 5_000_000_000 nanotons = 5 TON
        assert balance == Decimal("5")

    @pytest.mark.asyncio
    async def test_get_balance_ton_http_error(self, provider: TonWalletProvider) -> None:
        """HTTP non-200 response should return Decimal('0')."""
        mock_resp = AsyncMock()
        mock_resp.status = 500

        mock_get_cm = MagicMock()
        mock_get_cm.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_get_cm.__aexit__ = AsyncMock(return_value=None)

        mock_http = MagicMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=None)
        mock_http.get = MagicMock(return_value=mock_get_cm)

        with patch("providers.wallet_provider.aiohttp.ClientSession", return_value=mock_http):
            balance = await provider.get_balance("UQfakeaddress", "TON")

        assert balance == Decimal("0")

    @pytest.mark.asyncio
    async def test_get_balance_ton_not_ok_in_json(self, provider: TonWalletProvider) -> None:
        """JSON response with ok=False should return Decimal('0')."""
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value={"ok": False})

        mock_get_cm = MagicMock()
        mock_get_cm.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_get_cm.__aexit__ = AsyncMock(return_value=None)

        mock_http = MagicMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=None)
        mock_http.get = MagicMock(return_value=mock_get_cm)

        with patch("providers.wallet_provider.aiohttp.ClientSession", return_value=mock_http):
            balance = await provider.get_balance("UQfakeaddress", "TON")

        assert balance == Decimal("0")

    @pytest.mark.asyncio
    async def test_get_balance_ton_exception_returns_zero(
        self, provider: TonWalletProvider
    ) -> None:
        """Exception during HTTP call should be caught and return Decimal('0')."""
        with patch(
            "providers.wallet_provider.aiohttp.ClientSession", side_effect=Exception("Timeout")
        ):
            balance = await provider.get_balance("UQfakeaddress", "TON")

        assert balance == Decimal("0")


class TestTonWalletProviderTransfer:
    """Tests for TonWalletProvider.transfer() stub method."""

    @pytest.mark.asyncio
    async def test_transfer_returns_hex_string(self) -> None:
        """transfer() should return a hex string."""
        provider = TonWalletProvider(endpoint="https://fake-toncenter.com/jsonRPC")

        mock_wallet = MagicMock()
        mock_wallet.address.to_str.return_value = "fake_addr"

        mock_query = MagicMock()
        mock_query.message.to_boc.return_value.hex.return_value = "fake_boc"
        mock_query.message.hash.hex.return_value = "f" * 64
        mock_wallet.create_transfer_message.return_value = mock_query

        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value={"ok": True, "result": {"stack": [["num", "0x0"]]}})

        mock_post_cm = MagicMock()
        mock_post_cm.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_post_cm.__aexit__ = AsyncMock(return_value=None)

        mock_http = MagicMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=None)
        mock_http.post = MagicMock(return_value=mock_post_cm)

        with (
            patch("providers.wallet_provider.HAS_TON", True),
            patch("providers.wallet_provider.WalletV4R2") as mock_w_cls,
            patch("providers.wallet_provider.aiohttp.ClientSession", return_value=mock_http),
        ):
            mock_w_cls.from_private_key.return_value = mock_wallet

            result = await provider.transfer(
                private_key="0" * 64,  # valid 32-byte hex
                to_address="UQdestination",
                asset="TON",
                amount=Decimal("1.5"),
            )

        assert result == "f" * 64
