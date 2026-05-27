"""Tests for tasks/payout_worker.py — on-chain payout to seller after deal completion.

Strategy: patch async_session_factory at the module level so the function never
touches a real database. The deal object is a MagicMock (synchronous attributes),
which matches how SQLAlchemy ORM objects behave once loaded.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from db.models.product import CurrencyType
from db.models.wallet import WalletChain
from tasks.payout_worker import process_payout_to_seller

pytestmark = pytest.mark.unit


# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_deal(
    deal_id: uuid.UUID | None = None,
    currency_type: CurrencyType = CurrencyType.CRYPTO,
    blockchain: WalletChain | None = WalletChain.evm,
    payout_status: str | None = None,
    amount: Decimal = Decimal("10.00"),
    seller_id: int = 999,
    buyer_id: int = 888,
) -> MagicMock:
    """Build a mocked MarketplaceDeal for payout tests."""
    deal = MagicMock()
    deal.id = deal_id or uuid.uuid4()
    deal.currency_type = currency_type
    deal.blockchain = blockchain
    deal.payout_status = payout_status
    deal.amount = amount
    deal.seller_id = seller_id
    deal.buyer_id = buyer_id
    deal.product = MagicMock()
    deal.product.crypto_asset = "USDT"
    deal.tx_hash_release = None
    deal.payout_error = None
    deal.seller_wallet_address = None
    deal.network = "mainnet"
    return deal


def _make_seller_wallet(address: str = "0xSellerAddress") -> MagicMock:
    wallet = MagicMock()
    wallet.address = address
    wallet.chain = WalletChain.evm
    return wallet


def _build_session_ctx(
    deal: MagicMock | None,
    wallet: MagicMock | None = None,
) -> MagicMock:
    """Build a nested async context manager that mimics async_session_factory()."""
    session = AsyncMock()

    # scalar_one_or_none must be a regular method returning sync values
    execute_deal = MagicMock()
    execute_deal.scalar_one_or_none = MagicMock(return_value=deal)

    if wallet is not None:
        execute_wallet = MagicMock()
        execute_wallet.scalar_one_or_none = MagicMock(return_value=wallet)
        session.execute = AsyncMock(side_effect=[execute_deal, execute_wallet])
    else:
        session.execute = AsyncMock(return_value=execute_deal)

    # session.begin() returns an async context manager that does nothing
    begin_ctx = MagicMock()
    begin_ctx.__aenter__ = AsyncMock(return_value=session)
    begin_ctx.__aexit__ = AsyncMock(return_value=False)
    session.begin = MagicMock(return_value=begin_ctx)

    # async_session_factory() is itself an async context manager
    outer = MagicMock()
    outer.__aenter__ = AsyncMock(return_value=session)
    outer.__aexit__ = AsyncMock(return_value=False)
    return outer


# ── Deal not found ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_payout_deal_not_found_returns_early() -> None:
    """Returns immediately when deal does not exist in DB."""
    ctx = _build_session_ctx(deal=None)
    with patch("tasks.payout_worker.async_session_factory", return_value=ctx):
        await process_payout_to_seller(uuid.uuid4())

    # no transaction begin — returned early
    session = await ctx.__aenter__()
    session.begin.assert_not_called()


# ── Already processed (idempotency) ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_payout_already_sent_skips() -> None:
    """Skips processing when payout_status is already 'sent'."""
    deal = _make_deal(payout_status="sent")
    ctx = _build_session_ctx(deal=deal)
    with patch("tasks.payout_worker.async_session_factory", return_value=ctx):
        await process_payout_to_seller(deal.id)

    session = await ctx.__aenter__()
    session.begin.assert_not_called()


@pytest.mark.asyncio
async def test_payout_already_manual_skips() -> None:
    """Skips processing when payout_status is already 'manual'."""
    deal = _make_deal(payout_status="manual")
    ctx = _build_session_ctx(deal=deal)
    with patch("tasks.payout_worker.async_session_factory", return_value=ctx):
        await process_payout_to_seller(deal.id)

    session = await ctx.__aenter__()
    session.begin.assert_not_called()


# ── Stars (XTR) → manual payout ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_payout_xtr_sets_manual_status() -> None:
    """XTR (Stars) deals get payout_status set to 'manual'."""
    deal = _make_deal(currency_type=CurrencyType.XTR, payout_status=None)
    ctx = _build_session_ctx(deal=deal)
    with patch("tasks.payout_worker.async_session_factory", return_value=ctx):
        await process_payout_to_seller(deal.id)

    assert deal.payout_status == "manual"


# ── Crypto deal: no seller wallet ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_payout_no_seller_wallet_sets_failed() -> None:
    """Marks payout as failed when seller has no wallet on the deal's chain."""
    deal = _make_deal(currency_type=CurrencyType.CRYPTO, blockchain=WalletChain.evm)
    ctx = _build_session_ctx(deal=deal, wallet=None)
    with patch("tasks.payout_worker.async_session_factory", return_value=ctx):
        await process_payout_to_seller(deal.id)

    assert deal.payout_status == "failed"
    assert deal.payout_error is not None


# ── Crypto deal: successful transfer ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_payout_crypto_success_sets_sent_status() -> None:
    """Marks payout as 'sent' and stores tx_hash on successful transfer."""
    deal = _make_deal(currency_type=CurrencyType.CRYPTO, blockchain=WalletChain.evm)
    seller_wallet = _make_seller_wallet("0xSellerAddr")
    ctx = _build_session_ctx(deal=deal, wallet=seller_wallet)

    with (
        patch("tasks.payout_worker.async_session_factory", return_value=ctx),
        patch(
            "services.wallet_service.transfer_from_deal_wallet",
            new_callable=AsyncMock,
            return_value="0xdeadbeef",
        ),
        patch("services.marketplace_notifications.get_bot", return_value=AsyncMock()),
        patch(
            "services.marketplace_notifications.notify_seller_payout_sent",
            new_callable=AsyncMock,
        ),
    ):
        await process_payout_to_seller(deal.id)

    assert deal.payout_status == "sent"
    assert deal.tx_hash_release == "0xdeadbeef"


# ── Crypto deal: transfer fails ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_payout_transfer_failure_sets_failed_status() -> None:
    """Marks payout as 'failed' and stores error when blockchain transfer raises."""
    deal = _make_deal(currency_type=CurrencyType.CRYPTO, blockchain=WalletChain.evm)
    seller_wallet = _make_seller_wallet("0xSellerAddr")
    ctx = _build_session_ctx(deal=deal, wallet=seller_wallet)

    with (
        patch("tasks.payout_worker.async_session_factory", return_value=ctx),
        patch(
            "services.wallet_service.transfer_from_deal_wallet",
            new_callable=AsyncMock,
            side_effect=RuntimeError("RPC timeout"),
        ),
    ):
        await process_payout_to_seller(deal.id)

    assert deal.payout_status == "failed"
    assert "RPC timeout" in (deal.payout_error or "")


# ── Fatal outer error ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_payout_fatal_outer_error_does_not_propagate() -> None:
    """process_payout_to_seller never raises even on unexpected outer exceptions."""
    with patch(
        "tasks.payout_worker.async_session_factory",
        side_effect=Exception("DB connection failed"),
    ):
        # Must not raise
        await process_payout_to_seller(uuid.uuid4())
