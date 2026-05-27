"""Tests for tasks/marketplace_scanner.py — coverage boost."""

from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from db.models.product import CurrencyType, DealStatus, MarketplaceDeal, Product
from db.models.user import User
from tasks.marketplace_scanner import MarketplaceScanner

pytestmark = pytest.mark.integration


@pytest.fixture
def mock_bot() -> AsyncMock:
    return AsyncMock()



@pytest.fixture
def scanner(mock_bot: AsyncMock, engine: AsyncEngine) -> MarketplaceScanner:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    return MarketplaceScanner(bot=mock_bot, session_maker=factory, interval_sec=1)


@pytest.mark.asyncio
async def test_scanner_run_stop(scanner: MarketplaceScanner) -> None:
    """Scanner run and stop methods toggle the running state."""
    assert not scanner._running
    
    # We mock _scan_once to just stop the scanner so it doesn't loop forever
    async def mock_scan_once() -> None:
        scanner.stop()
        
    with patch.object(scanner, "_scan_once", new_callable=AsyncMock) as mock_scan:
        mock_scan.side_effect = mock_scan_once
        await scanner.run()
        
    assert not scanner._running
    mock_scan.assert_called_once()


@pytest.mark.asyncio
async def test_scan_once_no_deals(scanner: MarketplaceScanner, session: AsyncSession) -> None:
    """Scanner does nothing if there are no created deals."""
    await scanner._scan_once()
    # If no deals, it just returns without error
    assert True


@pytest.mark.asyncio
async def test_scan_once_with_created_deal(scanner: MarketplaceScanner, session: AsyncSession) -> None:
    """Scanner checks deposit for a created deal with blockchain and escrow."""
    buyer = User(telegram_id=111, username="buyer")
    seller = User(telegram_id=222, username="seller")
    session.add_all([buyer, seller])
    await session.commit()

    product = Product(
        id=uuid.uuid4(),
        seller_id=222,
        title="Test Product",
        description="Test desc",
        price=10.0,
        currency_type=CurrencyType.CRYPTO,
        crypto_asset="USDT",
    )
    session.add(product)
    await session.commit()

    deal_id = uuid.uuid4()
    from db.models.wallet import WalletChain

    deal = MarketplaceDeal(
        id=deal_id,
        product_id=product.id,
        buyer_id=111,
        seller_id=222,
        status=DealStatus.created,
        amount=10.0,
        currency_type=CurrencyType.CRYPTO,
        blockchain=WalletChain.evm,
        escrow_wallet_address="0x123",
        escrow_wallet_private_key_enc="mock",
    )
    session.add(deal)
    await session.commit()

    # Mock provider to return sufficient balance
    mock_provider = AsyncMock()
    mock_provider.get_balance.return_value = Decimal("10.0")

    with patch("tasks.marketplace_scanner._get_provider", return_value=mock_provider):
        await scanner._scan_once()

    # Check if deal status changed to paid
    await session.refresh(deal)
    assert deal.status == DealStatus.paid

    # Provider should have been called
    mock_provider.get_balance.assert_called_once_with("0x123", "USDT")


@pytest.mark.asyncio
async def test_scan_once_insufficient_balance(scanner: MarketplaceScanner, session: AsyncSession) -> None:
    """Scanner does not change status if balance is insufficient."""
    buyer = User(telegram_id=333, username="buyer3")
    seller = User(telegram_id=444, username="seller4")
    session.add_all([buyer, seller])
    await session.commit()

    product = Product(
        id=uuid.uuid4(),
        seller_id=444,
        title="Test Product 2",
        description="Test desc",
        price=20.0,
        currency_type=CurrencyType.CRYPTO,
        crypto_asset="TON",
    )
    session.add(product)
    await session.commit()

    deal_id = uuid.uuid4()
    from db.models.wallet import WalletChain

    deal = MarketplaceDeal(
        id=deal_id,
        product_id=product.id,
        buyer_id=333,
        seller_id=444,
        status=DealStatus.created,
        amount=20.0,
        currency_type=CurrencyType.CRYPTO,
        blockchain=WalletChain.ton,
        escrow_wallet_address="EQ123",
        escrow_wallet_private_key_enc="mock",
    )
    session.add(deal)
    await session.commit()

    # Mock provider to return insufficient balance
    mock_provider = AsyncMock()
    mock_provider.get_balance.return_value = Decimal("5.0")

    with patch("tasks.marketplace_scanner._get_provider", return_value=mock_provider):
        await scanner._scan_once()

    # Check deal status is still created
    await session.refresh(deal)
    assert deal.status == DealStatus.created
