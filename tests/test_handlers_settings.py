"""Tests for settings.py handlers."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from aiogram.types import Message
from sqlalchemy.ext.asyncio import async_sessionmaker

from bot.handlers import settings as settings_handlers
from db.models.user import User

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_cb_settings(engine) -> None:
    """Test showing the settings main menu."""
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        user = User(
            telegram_id=901,
            username="test_settings",
            notifications_enabled=True,
            default_fiat="RUB",
        )
        session.add(user)
        await session.commit()

    cb = AsyncMock()
    cb.message = AsyncMock(spec=Message)
    cb.message.text = "Menu"
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()

    await settings_handlers.cb_settings(cb, user)

    cb.message.edit_text.assert_called_once()
    args, kwargs = cb.message.edit_text.call_args
    assert "Settings & Preferences" in args[0]
    cb.answer.assert_called_once()


@pytest.mark.asyncio
async def test_cb_toggle_notif(engine) -> None:
    """Test toggling notification status."""
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        user = User(
            telegram_id=902, username="test_notif", notifications_enabled=True, default_fiat="RUB"
        )
        session.add(user)
        await session.commit()

    cb = AsyncMock()
    cb.message = AsyncMock(spec=Message)
    cb.message.text = "Menu"
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()

    async with factory() as session:
        await settings_handlers.cb_toggle_notif(cb, user, session)

    # Check DB
    async with factory() as session:
        db_user = await session.get(User, 902)
        assert db_user.notifications_enabled is False

    cb.message.edit_text.assert_called_once()
    cb.answer.assert_called_once_with("Notifications: OFF")


@pytest.mark.asyncio
async def test_cb_choose_fiat() -> None:
    """Test showing fiat selection menu."""
    cb = AsyncMock()
    cb.message = AsyncMock(spec=Message)
    cb.message.text = "Menu"
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()

    await settings_handlers.cb_choose_fiat(cb)

    cb.message.edit_text.assert_called_once()
    args, kwargs = cb.message.edit_text.call_args
    assert "Select Default Fiat Currency" in args[0]
    cb.answer.assert_called_once()


@pytest.mark.asyncio
async def test_cb_set_fiat(engine) -> None:
    """Test setting default fiat."""
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        user = User(
            telegram_id=903,
            username="test_set_fiat",
            notifications_enabled=True,
            default_fiat="RUB",
        )
        session.add(user)
        await session.commit()

    cb = AsyncMock()
    cb.message = AsyncMock(spec=Message)
    cb.data = "settings:set_fiat:USD"
    cb.message.text = "Menu"
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()

    async with factory() as session:
        await settings_handlers.cb_set_fiat(cb, user, session)

    # Check DB
    async with factory() as session:
        db_user = await session.get(User, 903)
        assert db_user.default_fiat == "USD"

    cb.message.edit_text.assert_called_once()
    args, kwargs = cb.message.edit_text.call_args
    assert "Default Fiat set to USD" in args[0]
    cb.answer.assert_called_once()
