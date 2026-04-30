"""Additional tests for wallet handlers and builders."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.handlers import wallet as wallet_handlers
from db.models.wallet import UserWallet
from services.balance_service import WalletBalance


@pytest.mark.asyncio
async def test_build_wallet_text_with_wallets(session: AsyncSession):
    with patch("bot.handlers.wallet.wallet_service.get_user_wallets") as mock_get:
        mock_get.return_value = [
            UserWallet(chain="evm", address="0x123"),
            UserWallet(chain="ton", address="UQabc"),
        ]
        text = await wallet_handlers._build_wallet_text(session, 1)
        assert "0x123" in text
        assert "UQabc" in text


@pytest.mark.asyncio
async def test_build_balance_text_with_error(session: AsyncSession):
    with patch("bot.handlers.wallet.balance_service.get_portfolio_balances") as mock_get:
        mock_get.return_value = [
            WalletBalance(
                wallet=UserWallet(chain="evm", address="0x123"),
                balances={},  # simulated error/unavailable
            )
        ]
        text = await wallet_handlers._build_balance_text(session, 1)
        assert "Balance unavailable" in text


@pytest.mark.asyncio
async def test_cb_wallet_add_handler():
    callback = AsyncMock(spec=CallbackQuery)
    callback.message = AsyncMock(spec=Message)
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()

    await wallet_handlers.cb_wallet_add(callback)
    callback.message.edit_text.assert_called_once()
    assert "Add Wallet" in callback.message.edit_text.call_args[0][0]
