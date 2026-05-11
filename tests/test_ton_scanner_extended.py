"""Extended tests for TONScanner."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from providers.ton import TONProvider
from tasks.ton_scanner import TONScanner


@pytest.mark.asyncio
async def test_ton_scanner_run_loop():
    provider = AsyncMock(spec=TONProvider)
    session_maker = MagicMock(spec=async_sessionmaker)

    scanner = TONScanner(provider, session_maker, "EQ_MASTER", interval_sec=0.1)

    # Mock _scan_once to raise an error to test exception handling in loop
    with patch.object(
        scanner, "_scan_once", side_effect=[None, Exception("loop error"), None]
    ) as mock_scan:
        # Run for a short time
        task = asyncio.create_task(scanner.run())
        await asyncio.sleep(0.3)
        scanner.stop()
        await task

        assert mock_scan.call_count >= 2
        assert scanner._running is False


@pytest.mark.asyncio
async def test_ton_scanner_run_already_running():
    scanner = TONScanner(AsyncMock(), MagicMock(), "EQ")
    scanner._running = True
    await scanner.run()  # Should return immediately
    assert scanner._running is True


@pytest.mark.asyncio
async def test_ton_scanner_scan_once_empty():
    provider = AsyncMock()
    provider.get_transactions.return_value = []
    scanner = TONScanner(provider, MagicMock(), "EQ")
    await scanner._scan_once()
    provider.get_transactions.assert_called_once()


@pytest.mark.asyncio
async def test_ton_scanner_scan_once_invalid_memo():
    provider = AsyncMock()
    provider.get_transactions.return_value = [
        {"memo": "short", "hash": "h", "amount_nanotons": 1, "utime": 1}
    ]
    session_maker = MagicMock()
    scanner = TONScanner(provider, session_maker, "EQ")
    await scanner._scan_once()
    # session_maker should be called if we found valid txs
    session_maker.assert_called_once()


@pytest.mark.asyncio
async def test_ton_scanner_scan_once_processing_error():
    provider = AsyncMock()
    provider.get_transactions.return_value = [
        {"memo": "LONG_ENOUGH_MEMO", "hash": "h", "amount_nanotons": 1, "utime": 1}
    ]

    session = AsyncMock(spec=AsyncSession)
    session_maker = MagicMock()
    session_maker.return_value.__aenter__.return_value = session

    scanner = TONScanner(provider, session_maker, "EQ")

    with patch(
        "tasks.ton_scanner.b2b_service.process_ton_payment", side_effect=Exception("process fail")
    ):
        await scanner._scan_once()
        # Should log warning and continue
