"""Tests for background scanners (EscrowScanner and MarketplaceScanner)."""

from __future__ import annotations

import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from db.models.order import Order, OrderStatus, OrderType
from db.models.product import DealStatus, MarketplaceDeal, Product
from db.models.user import User
from tasks.escrow_scanner import EscrowScanner
from tasks.marketplace_scanner import MarketplaceScanner


@pytest.mark.integration
@pytest.mark.asyncio
async def test_escrow_scanner_run_stop(session: AsyncSession) -> None:
    """EscrowScanner starts and stops cleanly."""
    bot = AsyncMock()
    session_maker = MagicMock(spec=async_sessionmaker)
    scanner = EscrowScanner(bot, session_maker, interval_sec=0.01)

    # Use a task to run it in background, then stop it
    run_task = asyncio.create_task(scanner.run())
    await asyncio.sleep(0.02)
    scanner.stop()
    await run_task
    assert not scanner._running


@pytest.mark.integration
@pytest.mark.asyncio
async def test_escrow_scanner_scan_once_empty(session: AsyncSession, engine) -> None:
    """EscrowScanner scan_once does nothing when no orders are pending."""
    bot = AsyncMock()
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    scanner = EscrowScanner(bot, session_maker)

    with patch.object(scanner, "_check_order_deposit", new_callable=AsyncMock) as mock_check:
        await scanner._scan_once()
        mock_check.assert_not_called()


@pytest.mark.filterwarnings("ignore::RuntimeWarning")
@pytest.mark.integration
@pytest.mark.asyncio
async def test_escrow_scanner_check_order_deposit_funded(session: AsyncSession, engine) -> None:
    """EscrowScanner activates order when balance is sufficient."""
    # Create test users and order
    async with session.begin():
        maker = User(telegram_id=3001, username="maker_escrow_scan")
        taker = User(telegram_id=3002, username="taker_escrow_scan")
        session.add(maker)
        session.add(taker)

    async with session.begin():
        order = Order(
            maker_id=3001,
            taker_id=3002,
            order_type=OrderType.sell_crypto,
            asset="USDT",
            amount=50.0,
            fiat_currency="USD",
            fiat_amount=50.0,
            payment_method="Card",
            status=OrderStatus.pending_funding,
            on_chain_status="awaiting_deposit",
            escrow_wallet_address="0xabc_escrow_scan_funded",
            on_chain_gas_buffer=0.01,
            spend_id="11111111-2222-3333-4444-555555555555",
        )
        session.add(order)

    bot = AsyncMock()
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    scanner = EscrowScanner(bot, session_maker)

    # Mock provider balance to be sufficient
    mock_provider = MagicMock()
    mock_provider.get_balance = AsyncMock(return_value=Decimal("50.02"))

    with (
        patch("tasks.escrow_scanner._get_provider", return_value=mock_provider),
        patch(
            "services.notification_service.notify_maker_order_activated", new_callable=AsyncMock
        ) as mock_notify_maker,
        patch(
            "services.notification_service.notify_taker_order_activated", new_callable=AsyncMock
        ) as mock_notify_taker,
    ):
        await scanner._scan_once()

        mock_notify_maker.assert_called_once()
        mock_notify_taker.assert_called_once()

        # Check order updated in DB
        async with session_maker() as sess:
            updated_order = await sess.get(Order, order.id)
            assert updated_order.status == OrderStatus.active
            assert updated_order.on_chain_status == "deposit_detected"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_escrow_scanner_check_order_deposit_insufficient(
    session: AsyncSession, engine
) -> None:
    """EscrowScanner leaves order pending when balance is insufficient."""
    async with session.begin():
        maker = User(telegram_id=3003, username="maker_escrow_scan_ins")
        session.add(maker)

    async with session.begin():
        order = Order(
            maker_id=3003,
            order_type=OrderType.sell_crypto,
            asset="USDT",
            amount=50.0,
            fiat_currency="USD",
            fiat_amount=50.0,
            payment_method="Card",
            status=OrderStatus.pending_funding,
            on_chain_status="awaiting_deposit",
            escrow_wallet_address="0xabc_escrow_scan_insufficient",
            on_chain_gas_buffer=0.01,
            spend_id="11111111-2222-3333-4444-666666666666",
        )
        session.add(order)

    bot = AsyncMock()
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    scanner = EscrowScanner(bot, session_maker)

    mock_provider = MagicMock()
    mock_provider.get_balance = AsyncMock(return_value=Decimal("49.99"))  # Less than 50.01

    with (
        patch("tasks.escrow_scanner._get_provider", return_value=mock_provider),
        patch(
            "services.notification_service.notify_maker_order_activated", new_callable=AsyncMock
        ) as mock_notify,
    ):
        await scanner._scan_once()
        mock_notify.assert_not_called()

        async with session_maker() as sess:
            updated_order = await sess.get(Order, order.id)
            assert updated_order.status == OrderStatus.pending_funding
            assert updated_order.on_chain_status == "awaiting_deposit"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_marketplace_scanner_run_stop(session: AsyncSession) -> None:
    """MarketplaceScanner starts and stops cleanly."""
    bot = AsyncMock()
    session_maker = MagicMock(spec=async_sessionmaker)
    scanner = MarketplaceScanner(bot, session_maker, interval_sec=0.01)

    run_task = asyncio.create_task(scanner.run())
    await asyncio.sleep(0.02)
    scanner.stop()
    await run_task
    assert not scanner._running


@pytest.mark.filterwarnings("ignore::RuntimeWarning")
@pytest.mark.integration
@pytest.mark.asyncio
async def test_marketplace_scanner_scan_once_empty(session: AsyncSession, engine) -> None:
    """MarketplaceScanner does nothing when no deals are created."""
    bot = AsyncMock()
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    scanner = MarketplaceScanner(bot, session_maker)

    with patch.object(scanner, "_check_deal_deposit", new_callable=AsyncMock) as mock_check:
        await scanner._scan_once()
        mock_check.assert_not_called()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_marketplace_scanner_check_deal_deposit_funded(session: AsyncSession, engine) -> None:
    """MarketplaceScanner marks deal paid when funded."""
    async with session.begin():
        seller = User(telegram_id=4001, username="seller_market_scan")
        buyer = User(telegram_id=4002, username="buyer_market_scan")
        session.add(seller)
        session.add(buyer)

    async with session.begin():
        from db.models.product import CurrencyType

        product = Product(
            seller_id=4001,
            title="Scan Product",
            description="Desc",
            price=Decimal("1.5"),
            currency_type=CurrencyType.CRYPTO,
            crypto_asset="TON",
        )
        session.add(product)

    async with session.begin():
        deal = MarketplaceDeal(
            product_id=product.id,
            buyer_id=4002,
            seller_id=4001,
            amount=Decimal("1.5"),
            status=DealStatus.created,
            escrow_wallet_address="EQScanWalletFunded",
            blockchain="ton",
            currency_type=CurrencyType.CRYPTO,
        )
        session.add(deal)

    bot = AsyncMock()
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    scanner = MarketplaceScanner(bot, session_maker)

    mock_provider = MagicMock()
    mock_provider.get_balance = AsyncMock(return_value=Decimal("1.5"))

    with (
        patch("tasks.marketplace_scanner._get_provider", return_value=mock_provider),
        patch("tasks.marketplace_scanner.notify_deal_paid", new_callable=AsyncMock) as mock_notify,
    ):
        await scanner._scan_once()
        await asyncio.sleep(0.01)  # Allow background tasks to run

        mock_notify.assert_called_once()

        async with session_maker() as sess:
            updated_deal = await sess.get(MarketplaceDeal, deal.id)
            assert updated_deal.status == DealStatus.paid


@pytest.mark.integration
@pytest.mark.asyncio
async def test_marketplace_scanner_check_deal_deposit_insufficient(
    session: AsyncSession, engine
) -> None:
    """MarketplaceScanner leaves deal created when deposit is insufficient."""
    async with session.begin():
        seller = User(telegram_id=4003, username="seller_market_scan_ins")
        buyer = User(telegram_id=4004, username="buyer_market_scan_ins")
        session.add(seller)
        session.add(buyer)

    async with session.begin():
        from db.models.product import CurrencyType

        product = Product(
            seller_id=4003,
            title="Scan Product Insufficient",
            description="Desc",
            price=Decimal("2.0"),
            currency_type=CurrencyType.CRYPTO,
            crypto_asset="TON",
        )
        session.add(product)

    async with session.begin():
        deal = MarketplaceDeal(
            product_id=product.id,
            buyer_id=4004,
            seller_id=4003,
            amount=Decimal("2.0"),
            status=DealStatus.created,
            escrow_wallet_address="EQScanWalletInsufficient",
            blockchain="ton",
            currency_type=CurrencyType.CRYPTO,
        )
        session.add(deal)

    bot = AsyncMock()
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    scanner = MarketplaceScanner(bot, session_maker)

    mock_provider = MagicMock()
    mock_provider.get_balance = AsyncMock(return_value=Decimal("1.99"))

    with (
        patch("tasks.marketplace_scanner._get_provider", return_value=mock_provider),
        patch("tasks.marketplace_scanner.notify_deal_paid", new_callable=AsyncMock) as mock_notify,
    ):
        await scanner._scan_once()
        mock_notify.assert_not_called()

        async with session_maker() as sess:
            updated_deal = await sess.get(MarketplaceDeal, deal.id)
            assert updated_deal.status == DealStatus.created
