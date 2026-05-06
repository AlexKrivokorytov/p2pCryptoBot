"""Tests for bot/main.py — startup, shutdown and configuration."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_main_full_startup_and_shutdown() -> None:
    """main() should start polling and perform clean shutdown."""
    # Mock all external dependencies
    mock_engine = MagicMock()
    mock_engine.dispose = AsyncMock()

    mock_session_pool = MagicMock()

    mock_bot = MagicMock()
    mock_bot.session = MagicMock()
    mock_bot.session.close = AsyncMock()

    mock_dp = MagicMock()
    mock_dp.update = MagicMock()
    mock_dp.update.outer_middleware = MagicMock()
    mock_dp.include_router = MagicMock()
    mock_dp.resolve_used_update_types = MagicMock(return_value=[])
    mock_dp.start_polling = AsyncMock()

    mock_crypto_pay = MagicMock()
    mock_crypto_pay.close = AsyncMock()

    mock_site = MagicMock()
    mock_site.start = AsyncMock()

    mock_runner = MagicMock()
    mock_runner.setup = AsyncMock()
    mock_runner.cleanup = AsyncMock()

    mock_cleanup_task = asyncio.create_task(asyncio.sleep(0))

    mock_i18n = MagicMock()
    mock_i18n.setup = MagicMock()

    with (
        patch("bot.main.check_license_or_abort"),
        patch("bot.main.create_async_engine", return_value=mock_engine),
        patch("bot.main.async_sessionmaker", return_value=mock_session_pool),
        patch("bot.main.CryptoPayClient", return_value=mock_crypto_pay),
        patch("bot.main.Bot", return_value=mock_bot),
        patch("bot.main.Dispatcher", return_value=mock_dp),
        patch("bot.main.web.Application", return_value=MagicMock()),
        patch("bot.main.web.AppRunner", return_value=mock_runner),
        patch("bot.main.web.TCPSite", return_value=mock_site),
        patch("bot.main.asyncio.create_task", return_value=mock_cleanup_task),
        patch("bot.main.setup_i18n", return_value=mock_i18n),
        patch("bot.main.start_cleanup_task", new_callable=AsyncMock),
        patch("bot.main.ROUTERS", []),
    ):
        from bot.main import main

        await main()

    mock_dp.start_polling.assert_awaited_once()
    mock_engine.dispose.assert_awaited_once()
    mock_runner.cleanup.assert_awaited_once()
    mock_crypto_pay.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_main_shutdown_on_polling_exception() -> None:
    """main() should cleanup even when polling raises an exception."""
    mock_engine = MagicMock()
    mock_engine.dispose = AsyncMock()

    mock_bot = MagicMock()
    mock_bot.session = MagicMock()
    mock_bot.session.close = AsyncMock()

    mock_dp = MagicMock()
    mock_dp.update = MagicMock()
    mock_dp.update.outer_middleware = MagicMock()
    mock_dp.include_router = MagicMock()
    mock_dp.resolve_used_update_types = MagicMock(return_value=[])
    # Simulate polling raising an error
    mock_dp.start_polling = AsyncMock(side_effect=KeyboardInterrupt)

    mock_crypto_pay = MagicMock()
    mock_crypto_pay.close = AsyncMock()

    mock_site = MagicMock()
    mock_site.start = AsyncMock()

    mock_runner = MagicMock()
    mock_runner.setup = AsyncMock()
    mock_runner.cleanup = AsyncMock()

    mock_cleanup_task = asyncio.create_task(asyncio.sleep(0))
    mock_i18n = MagicMock()
    mock_i18n.setup = MagicMock()

    with (
        patch("bot.main.check_license_or_abort"),
        patch("bot.main.create_async_engine", return_value=mock_engine),
        patch("bot.main.async_sessionmaker", return_value=MagicMock()),
        patch("bot.main.CryptoPayClient", return_value=mock_crypto_pay),
        patch("bot.main.Bot", return_value=mock_bot),
        patch("bot.main.Dispatcher", return_value=mock_dp),
        patch("bot.main.web.Application", return_value=MagicMock()),
        patch("bot.main.web.AppRunner", return_value=mock_runner),
        patch("bot.main.web.TCPSite", return_value=mock_site),
        patch("bot.main.asyncio.create_task", return_value=mock_cleanup_task),
        patch("bot.main.setup_i18n", return_value=mock_i18n),
        patch("bot.main.start_cleanup_task", new_callable=AsyncMock),
        patch("bot.main.ROUTERS", []),
    ):
        from bot import main as main_module

        with pytest.raises(KeyboardInterrupt):
            await main_module.main()

    # Cleanup must still be called
    mock_runner.cleanup.assert_awaited_once()
    mock_engine.dispose.assert_awaited_once()
