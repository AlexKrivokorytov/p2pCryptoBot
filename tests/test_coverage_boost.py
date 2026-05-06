"""Coverage boost for remaining edge cases in handlers and main.py."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import CallbackQuery, Message

from bot.handlers.admin import (
    cb_admin_disputes,
    cb_dispute_resolve,
    cb_dispute_view,
    cmd_admin,
    cmd_stats,
)
from bot.handlers.wallet import (
    cb_generate_wallet,
    cb_wallet,
    cb_wallet_add,
    cb_wallet_balance,
    cmd_wallet,
)


@pytest.mark.asyncio
async def test_admin_handlers_no_user() -> None:
    """Test admin handlers when message.from_user is None."""
    msg = MagicMock(spec=Message)
    msg.from_user = None
    msg.answer = AsyncMock()

    await cmd_admin(msg)
    msg.answer.assert_called_with("⛔ Admins only.")

    await cmd_stats(msg, MagicMock())
    msg.answer.assert_called_with("⛔ Admins only.")


@pytest.mark.asyncio
async def test_admin_callbacks_no_message() -> None:
    """Test admin callbacks when callback.message is not a Message."""
    cb = MagicMock(spec=CallbackQuery)
    cb.message = None  # Not a Message
    cb.data = "admin:dispute:view:order_id"
    cb.from_user = MagicMock(id=123)
    cb.answer = AsyncMock()

    await cb_admin_disputes(cb, MagicMock())
    cb.answer.assert_called_with("⛔ Admins only.", show_alert=True)

    await cb_dispute_view(cb, MagicMock())
    cb.answer.assert_called_with("⛔ Admins only.", show_alert=True)

    # Resolve handler just returns
    assert await cb_dispute_resolve(cb, MagicMock(), MagicMock(), MagicMock()) is None


@pytest.mark.asyncio
async def test_wallet_handlers_no_user_or_msg() -> None:
    """Test wallet handlers with missing user or message."""
    msg = MagicMock(spec=Message)
    msg.from_user = None
    assert await cmd_wallet(msg, MagicMock()) is None

    cb = MagicMock(spec=CallbackQuery)
    cb.message = None
    cb.data = "some:data"
    assert await cb_wallet(cb, MagicMock()) is None
    assert await cb_wallet_balance(cb, MagicMock()) is None
    assert await cb_wallet_add(cb) is None
    assert await cb_generate_wallet(cb, MagicMock(), MagicMock()) is None
