"""Tests for bot middleware."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.types import CallbackQuery, Message, TelegramObject, User

from bot.middleware import (
    BrandingMiddleware,
    CryptoPayMiddleware,
    DbSessionMiddleware,
    ThrottlingMiddleware,
    UserRegistrationMiddleware,
)

pytestmark = pytest.mark.unit


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


@pytest.mark.asyncio
async def test_throttling_middleware_rate_limit() -> None:
    middleware = ThrottlingMiddleware(rate_limit=0.5)
    handler = AsyncMock(return_value="success")

    # Create a message event
    user = User(id=123, is_bot=False, first_name="Test")
    event = MagicMock(spec=Message)
    event.from_user = user
    data = {}

    # First call should succeed
    res1 = await middleware(handler, event, data)
    assert res1 == "success"
    assert handler.call_count == 1

    # Second call immediately should fail
    res2 = await middleware(handler, event, data)
    assert res2 is None
    assert handler.call_count == 1

    # Wait for rate limit to pass
    time.sleep(0.6)

    # Third call should succeed
    res3 = await middleware(handler, event, data)
    assert res3 == "success"
    assert handler.call_count == 2


@pytest.mark.asyncio
async def test_throttling_middleware_callback_query() -> None:
    middleware = ThrottlingMiddleware(rate_limit=1.0)
    handler = AsyncMock(return_value="success")

    user = User(id=456, is_bot=False, first_name="Test")
    event = AsyncMock(spec=CallbackQuery)
    event.from_user = user
    event.answer = AsyncMock()
    data = {}

    # First call succeeds
    await middleware(handler, event, data)
    assert handler.call_count == 1

    # Second call throttled, should answer callback
    await middleware(handler, event, data)
    assert handler.call_count == 1
    event.answer.assert_called_once_with("⚠️ Slow down!", show_alert=True)


@pytest.mark.asyncio
async def test_user_registration_middleware() -> None:
    middleware = UserRegistrationMiddleware()
    handler = AsyncMock(return_value="success")

    user = User(id=789, is_bot=False, first_name="Test User", username="testuser")
    event = MagicMock(spec=Message)
    event.from_user = user

    session = AsyncMock()
    data = {"session": session}

    with patch(
        "services.user_service.get_or_create_user", new_callable=AsyncMock
    ) as mock_get_or_create:
        mock_db_user = MagicMock()
        mock_get_or_create.return_value = mock_db_user

        await middleware(handler, event, data)

        mock_get_or_create.assert_called_once_with(
            session, telegram_id=789, username="testuser", first_name="Test User"
        )
        assert data["db_user"] == mock_db_user
        assert handler.call_count == 1


@pytest.mark.asyncio
async def test_branding_middleware_with_license() -> None:
    middleware = BrandingMiddleware()
    handler = AsyncMock(return_value="success")

    event = MagicMock(spec=Message)
    session = AsyncMock()
    data = {"session": session, "license_id": "test_license_uuid"}

    with (
        patch("bot.config.load_license_branding", new_callable=AsyncMock) as mock_load,
        patch("bot.config.set_branding") as mock_set,
    ):
        mock_branding = {"bot": {"name": "B2B Bot"}}
        mock_load.return_value = mock_branding

        await middleware(handler, event, data)

        mock_load.assert_called_once_with(session, "test_license_uuid")
        mock_set.assert_called_once_with(mock_branding)
        assert handler.call_count == 1


@pytest.mark.asyncio
async def test_branding_middleware_no_license() -> None:
    middleware = BrandingMiddleware()
    handler = AsyncMock(return_value="success")

    event = MagicMock(spec=Message)
    data = {"session": AsyncMock()}  # Missing license_id

    with (
        patch("bot.config.load_branding") as mock_load,
        patch("bot.config.set_branding") as mock_set,
    ):
        mock_branding = {"bot": {"name": "Master Bot"}}
        mock_load.return_value = mock_branding

        await middleware(handler, event, data)

        mock_load.assert_called_once()
        mock_set.assert_called_once_with(mock_branding)
        assert handler.call_count == 1
