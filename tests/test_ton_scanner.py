"""B2B Phase 4 tests — TON scanner and payment processing."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from providers.wallet_provider import TonWalletProvider as TONProvider
from services import b2b_service
from tasks.ton_scanner import TONScanner

pytestmark = pytest.mark.b2b


@pytest.mark.asyncio
async def test_ton_scanner_scan_once():
    # Mock dependencies
    provider = AsyncMock(spec=TONProvider)
    session_maker = MagicMock(spec=async_sessionmaker)
    session = AsyncMock(spec=AsyncSession)
    session_maker.return_value.__aenter__.return_value = session

    scanner = TONScanner(provider, session_maker, "EQ_MASTER_WALLET")

    # Mock transactions
    provider.get_transactions.return_value = [
        {
            "hash": "tx_hash_1",
            "amount_nanotons": 1000000000,
            "memo": "MEMO_LONG_ENOUGH",
            "utime": 1600000000,
        }
    ]

    with patch(
        "tasks.ton_scanner.b2b_service.process_ton_payment", new_callable=AsyncMock
    ) as mock_process:
        await scanner._scan_once()

        mock_process.assert_called_once_with(
            session,
            memo="MEMO_LONG_ENOUGH",
            tx_hash="tx_hash_1",
            amount_nanotons=1000000000,
            utime=1600000000,
        )


@pytest.mark.asyncio
async def test_process_ton_payment_success(session: AsyncSession):
    # Create user first (Foreign Key constraint)
    from services.user_service import get_or_create_user

    await get_or_create_user(session, telegram_id=12345, username="testuser")
    await session.commit()

    # Setup invoice in DB
    invoice = await b2b_service.create_ton_invoice(session, user_id=12345, amount_ton=10.0)
    memo = invoice["memo"]

    # Mock create_b2b_license to avoid real DB mutations inside the call
    # (actually create_b2b_license is in the same module, so we patch it)
    with patch("services.b2b_service.create_b2b_license", new_callable=AsyncMock) as mock_license:
        mock_license.return_value = {"license_id": "lic_123", "expires_at": datetime.now()}

        # 10.0 TON = 10,000,000,000 nanotons
        result = await b2b_service.process_ton_payment(
            session,
            memo=memo,
            tx_hash="some_tx_hash",
            amount_nanotons=10_000_000_000,
            utime=int(datetime.now().timestamp()),
        )

        assert result is True
        # Verify invoice status changed to paid
        from sqlalchemy import select

        from db.models.b2b import TONInvoice

        res = await session.execute(select(TONInvoice).where(TONInvoice.memo == memo))
        db_invoice = res.scalar_one()
        assert db_invoice.status == "paid"
        assert db_invoice.tx_hash == "some_tx_hash"


@pytest.mark.asyncio
async def test_process_ton_payment_insufficient_amount(session: AsyncSession):
    # Create user first
    from services.user_service import get_or_create_user

    await get_or_create_user(session, telegram_id=12345, username="testuser")
    await session.commit()

    invoice = await b2b_service.create_ton_invoice(session, user_id=12345, amount_ton=10.0)
    memo = invoice["memo"]

    # Send only 1 TON
    result = await b2b_service.process_ton_payment(
        session,
        memo=memo,
        tx_hash="some_tx_hash",
        amount_nanotons=1_000_000_000,
        utime=int(datetime.now().timestamp()),
    )

    assert result is False


@pytest.mark.asyncio
async def test_get_ton_license_price():
    with patch("services.b2b_service.get_market_rate", new_callable=AsyncMock) as mock_rate:
        # If TON is $5, price should be 20 TON
        mock_rate.return_value = 5.0
        price = await b2b_service.get_ton_license_price()
        assert price == 20.0

        # If rate lookup fails, fallback to 20.0
        mock_rate.return_value = None
        price = await b2b_service.get_ton_license_price()
        assert price == 20.0


@pytest.mark.asyncio
async def test_ton_scanner_run_loop():
    """TON scanner run loop should handle exceptions and continue."""
    import asyncio

    provider = AsyncMock(spec=TONProvider)
    session_maker = MagicMock(spec=async_sessionmaker)

    scanner = TONScanner(provider, session_maker, "EQ_MASTER", interval_sec=0.1)

    # Mock _scan_once to raise an error then stop
    with patch.object(
        scanner, "_scan_once", side_effect=[None, Exception("loop error"), None]
    ) as mock_scan:
        task = asyncio.create_task(scanner.run())
        await asyncio.sleep(0.3)
        scanner.stop()
        await task

        assert mock_scan.call_count >= 2
        assert scanner._running is False


@pytest.mark.asyncio
async def test_ton_scanner_run_already_running():
    """TON scanner should return immediately if already running."""
    scanner = TONScanner(AsyncMock(), MagicMock(), "EQ")
    scanner._running = True
    await scanner.run()
    assert scanner._running
