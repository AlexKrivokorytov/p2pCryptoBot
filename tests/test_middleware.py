"""Tests for bot middleware."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import TelegramObject

from bot.middleware import CryptoPayMiddleware, DbSessionMiddleware


@pytest.mark.asyncio
async def test_db_session_middleware() -> None:
    """Test DbSessionMiddleware injects session and calls handler."""
    session_pool = MagicMock()
    session = AsyncMock()
    session_pool.return_value.__aenter__.return_value = session

    middleware = DbSessionMiddleware(session_pool)
    handler = AsyncMock()
    event = MagicMock(spec=TelegramObject)
    data = {}

    await middleware(handler, event, data)

    assert "session" in data
    assert data["session"] == session
    handler.assert_called_once_with(event, data)


@pytest.mark.asyncio
async def test_crypto_pay_middleware() -> None:
    """Test CryptoPayMiddleware injects client and calls handler."""
    client = MagicMock()
    middleware = CryptoPayMiddleware(client)
    handler = AsyncMock()
    event = MagicMock(spec=TelegramObject)
    data = {}

    await middleware(handler, event, data)

    assert "crypto_pay" in data
    assert data["crypto_pay"] == client
    handler.assert_called_once_with(event, data)
