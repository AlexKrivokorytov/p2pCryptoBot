"""Tests for bot/main.py — coverage boost for the main entry point."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_main_execution() -> None:
    """Test the main() function by mocking polling and webhook server."""
    # Mock all the components that main() initializes
    mock_bot = MagicMock()
    mock_bot.session.close = AsyncMock()
    mock_dp = MagicMock()
    mock_runner = MagicMock()
    mock_runner.setup = AsyncMock()
    mock_runner.cleanup = AsyncMock()

    mock_site = MagicMock()
    mock_site.start = AsyncMock()
    mock_cp = MagicMock()
    mock_cp.close = AsyncMock()

    with (
        patch("bot.main.Bot", return_value=mock_bot),
        patch("bot.main.Dispatcher", return_value=mock_dp),
        patch("bot.main.web.AppRunner", return_value=mock_runner),
        patch("bot.main.web.TCPSite", return_value=mock_site),
        patch("bot.main.setup_i18n"),
        patch("bot.main.check_license_or_abort"),
        patch("bot.main.create_async_engine") as mock_create_engine,
        patch("bot.main.async_sessionmaker"),
        patch("bot.main.CryptoPayClient", return_value=mock_cp),
        patch("bot.main.start_cleanup_task") as mock_cleanup_start,
        patch("bot.main.ROUTERS", [MagicMock()]),
    ):
        # Mock engine
        mock_engine = MagicMock()
        mock_engine.dispose = AsyncMock()
        mock_create_engine.return_value = mock_engine

        # Mock cleanup task to be a real task that finishes
        async def fake_cleanup(sp):
            await asyncio.sleep(0.01)
        mock_cleanup_start.side_effect = fake_cleanup

        # Mock polling to finish immediately
        mock_dp.start_polling = AsyncMock()

        from bot.main import main
        await main()

        # Verify components were initialized and closed
        mock_dp.include_router.assert_called()
        mock_dp.start_polling.assert_called_once()
        mock_cp.close.assert_called_once()
        mock_engine.dispose.assert_called_once()
