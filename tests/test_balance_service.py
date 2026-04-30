"""Tests for balance_service and updated wallet handler balance flow."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.wallet import UserWallet, WalletChain
from services import balance_service


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_wallet(chain: str, address: str) -> UserWallet:
    return UserWallet(
        id=1, user_id=100, chain=chain,
        address=address, encrypted_private_key="enc",
    )


# ── balance_service.get_portfolio_balances ────────────────────────────────────

@pytest.mark.asyncio
@patch("services.balance_service.ws.get_user_wallets", new_callable=AsyncMock)
async def test_portfolio_empty_wallets(
    mock_get: AsyncMock, session: AsyncSession
) -> None:
    """Returns empty list when user has no wallets."""
    mock_get.return_value = []
    result = await balance_service.get_portfolio_balances(session, user_id=1)
    assert result == []


@pytest.mark.asyncio
@patch("services.balance_service.ws.get_user_wallets", new_callable=AsyncMock)
@patch("services.balance_service._fetch_single_balance", new_callable=AsyncMock)
async def test_portfolio_evm_balances(
    mock_fetch: AsyncMock,
    mock_get: AsyncMock,
    session: AsyncSession,
) -> None:
    """Returns WalletBalance objects with fetched amounts for EVM wallet."""
    wallet = _make_wallet("evm", "0xTestAddress")
    mock_get.return_value = [wallet]

    # Simulate fetch results per asset
    mock_fetch.side_effect = [
        ("BNB", Decimal("0.5")),
        ("USDT", Decimal("100.0")),
        ("USDC", Decimal("0")),
    ]

    results = await balance_service.get_portfolio_balances(session, user_id=100)

    assert len(results) == 1
    wb = results[0]
    assert wb.wallet.address == "0xTestAddress"
    assert wb.balances["BNB"] == Decimal("0.5")
    assert wb.balances["USDT"] == Decimal("100.0")
    assert wb.balances["USDC"] == Decimal("0")


@pytest.mark.asyncio
@patch("services.balance_service.ws.get_user_wallets", new_callable=AsyncMock)
@patch("services.balance_service._fetch_single_balance", new_callable=AsyncMock)
async def test_portfolio_ton_balances(
    mock_fetch: AsyncMock,
    mock_get: AsyncMock,
    session: AsyncSession,
) -> None:
    """Returns WalletBalance objects with TON amount."""
    wallet = _make_wallet("ton", "UQTestTonAddress")
    mock_get.return_value = [wallet]
    mock_fetch.side_effect = [("TON", Decimal("5.123456789"))]

    results = await balance_service.get_portfolio_balances(session, user_id=100)

    assert len(results) == 1
    assert results[0].balances["TON"] == Decimal("5.123456789")


@pytest.mark.asyncio
@patch("services.balance_service.ws.get_user_wallets", new_callable=AsyncMock)
@patch("services.balance_service._fetch_single_balance", new_callable=AsyncMock)
async def test_portfolio_multiple_wallets(
    mock_fetch: AsyncMock,
    mock_get: AsyncMock,
    session: AsyncSession,
) -> None:
    """Handles multiple wallets (one EVM, one TON) correctly."""
    evm = _make_wallet("evm", "0xEvmAddr")
    ton = _make_wallet("ton", "UQTonAddr")
    mock_get.return_value = [evm, ton]

    mock_fetch.side_effect = [
        ("BNB", Decimal("1.0")),
        ("USDT", Decimal("50.0")),
        ("USDC", Decimal("0")),
        ("TON", Decimal("2.5")),
    ]

    results = await balance_service.get_portfolio_balances(session, user_id=100)
    assert len(results) == 2
    assert results[0].wallet.chain == "evm"
    assert results[1].wallet.chain == "ton"


# ── _fetch_single_balance timeout protection ──────────────────────────────────

@pytest.mark.asyncio
@patch("services.balance_service._get_provider")
async def test_fetch_single_balance_timeout(mock_get_provider: MagicMock) -> None:
    """Timeout returns (asset, Decimal('0')) without raising."""
    import asyncio

    provider = AsyncMock()

    async def slow_balance(*args, **kwargs):  # type: ignore[no-untyped-def]
        await asyncio.sleep(100)  # simulates RPC hang
        return Decimal("1.0")

    provider.get_balance.side_effect = slow_balance
    mock_get_provider.return_value = provider

    wallet = _make_wallet("evm", "0xSlowAddr")
    # Override timeout to 0.01s so test runs fast
    original = balance_service._BALANCE_TIMEOUT_SEC
    balance_service._BALANCE_TIMEOUT_SEC = 0.01  # type: ignore[assignment]
    try:
        asset, amount = await balance_service._fetch_single_balance(wallet, "BNB")
    finally:
        balance_service._BALANCE_TIMEOUT_SEC = original  # type: ignore[assignment]

    assert asset == "BNB"
    assert amount == Decimal("0")


@pytest.mark.asyncio
@patch("services.balance_service._get_provider")
async def test_fetch_single_balance_exception(mock_get_provider: MagicMock) -> None:
    """RPC exception returns (asset, Decimal('0')) without raising."""
    provider = AsyncMock()
    provider.get_balance.side_effect = ConnectionError("RPC unavailable")
    mock_get_provider.return_value = provider

    wallet = _make_wallet("evm", "0xBadAddr")
    asset, amount = await balance_service._fetch_single_balance(wallet, "BNB")

    assert asset == "BNB"
    assert amount == Decimal("0")


# ── Handler: cb_wallet_balance ────────────────────────────────────────────────

@pytest.mark.asyncio
@patch("bot.handlers.wallet.balance_service.get_portfolio_balances", new_callable=AsyncMock)
async def test_cb_wallet_balance_no_wallets(
    mock_portfolio: AsyncMock, session: AsyncSession
) -> None:
    """Balance callback shows empty-state message when no wallets."""
    from bot.handlers import wallet as wallet_handlers

    mock_portfolio.return_value = []

    callback = AsyncMock()
    callback.from_user.id = 111

    await wallet_handlers.cb_wallet_balance(callback, session)

    assert callback.message.edit_text.call_count == 2  # "loading…" + result
    final_call = callback.message.edit_text.call_args_list[-1]
    text = final_call[0][0] if final_call[0] else final_call[1].get("text", "")
    assert "Wallet" in text


@pytest.mark.asyncio
@patch("bot.handlers.wallet.balance_service.get_portfolio_balances", new_callable=AsyncMock)
async def test_cb_wallet_balance_with_balance(
    mock_portfolio: AsyncMock, session: AsyncSession
) -> None:
    """Balance callback shows amounts when wallets have balance."""
    from bot.handlers import wallet as wallet_handlers
    from services.balance_service import WalletBalance

    wallet = _make_wallet("evm", "0xRichAddr")
    mock_portfolio.return_value = [
        WalletBalance(
            wallet=wallet,
            balances={"BNB": Decimal("1.5"), "USDT": Decimal("250.0"), "USDC": Decimal("0")},
        )
    ]

    callback = AsyncMock()
    callback.from_user.id = 111

    await wallet_handlers.cb_wallet_balance(callback, session)

    final_call = callback.message.edit_text.call_args_list[-1]
    text = final_call[0][0] if final_call[0] else final_call[1].get("text", "")
    assert "BNB" in text
    assert "1.5" in text
    assert "USDT" in text
    assert "250" in text
