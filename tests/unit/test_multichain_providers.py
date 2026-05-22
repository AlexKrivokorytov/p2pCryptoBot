from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from providers.wallet_provider import SolanaWalletProvider, TronWalletProvider


@pytest.mark.unit
async def test_solana_provider_keygen():
    provider = SolanaWalletProvider()
    try:
        wallet = await provider.generate_wallet(123)
        assert "address" in wallet
        assert "private_key" in wallet
        assert len(wallet["address"]) > 30
    except ImportError:
        pytest.skip("solana-py not installed")


@pytest.mark.unit
async def test_tron_provider_keygen():
    # Since we installed tronpy --no-deps, we should check if it works
    provider = TronWalletProvider()
    try:
        wallet = await provider.generate_wallet(123)
        assert "address" in wallet
        assert "private_key" in wallet
        assert wallet["address"].startswith("T")
    except ImportError:
        pytest.skip("tronpy not working without deps")


@pytest.mark.unit
async def test_solana_get_balance_sol():
    provider = SolanaWalletProvider()
    try:
        with patch(
            "solana.rpc.async_api.AsyncClient.get_balance", new_callable=AsyncMock
        ) as mock_get:
            mock_get.return_value.value = 10**9  # 1 SOL
            balance = await provider.get_balance(
                "BPaVATaMSkRYrAnaEp4ExBYHkyEGbjoa2Y9LjJzY8dfE", "SOL"
            )
            assert balance == Decimal("1")
    except ImportError:
        pytest.skip("solana-py not installed")
