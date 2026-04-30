"""Extra tests for handlers to reach 95% coverage."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch, ANY
import uuid
from datetime import datetime, UTC
from decimal import Decimal
import pytest
from aiogram.types import Message, CallbackQuery, User
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from bot.handlers import admin as admin_handlers
from bot.handlers import wallet as wallet_handlers
from bot.handlers import order as order_handlers
from db.models.order import Order
from db.models.wallet import UserWallet
from services.admin_service import PlatformStats


@pytest.mark.asyncio
@patch("bot.handlers.admin.admin_service.get_platform_stats", new_callable=AsyncMock)
@patch("bot.handlers.admin._is_admin", return_value=True)
async def test_admin_stats_refresh(mock_is_admin: MagicMock, mock_stats: AsyncMock, session: AsyncSession):
    callback = AsyncMock(spec=CallbackQuery)
    callback.from_user = MagicMock(spec=User)
    callback.from_user.id = 999
    callback.message = AsyncMock(spec=Message)
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()
    callback.data = "admin:stats:refresh"
    
    mock_stats.return_value = PlatformStats(
        total_orders=10, active_orders=2, escrow_held_orders=1,
        completed_orders=5, cancelled_orders=1, dispute_orders=1,
        pending_funding_orders=0, total_volume_completed=1000.0,
        unique_makers=3, unique_takers=2, generated_at=datetime.now(UTC)
    )
    await admin_handlers.cb_admin_stats(callback, session)
    callback.message.edit_text.assert_called()
    callback.answer.assert_called()


@pytest.mark.asyncio
@patch("bot.handlers.admin.admin_service.get_dispute_queue", new_callable=AsyncMock)
@patch("bot.handlers.admin._is_admin", return_value=True)
async def test_admin_disputes_list(mock_is_admin: MagicMock, mock_disputes: AsyncMock, session: AsyncSession):
    message = AsyncMock(spec=Message)
    message.from_user = MagicMock(spec=User)
    message.from_user.id = 999
    message.answer = AsyncMock()
    
    order = Order(
        id=uuid.uuid4(), 
        asset="TON", 
        amount=Decimal("1.5"),
        maker_id=1,
        taker_id=2
    )
    mock_disputes.return_value = [order]
    await admin_handlers.cmd_disputes(message, session)
    message.answer.assert_called()


@pytest.mark.asyncio
async def test_cb_wallet_generate_invalid_chain():
    callback = AsyncMock(spec=CallbackQuery)
    callback.from_user = MagicMock(spec=User)
    callback.from_user.id = 123
    callback.data = "wallet:generate:invalid"
    callback.message = AsyncMock(spec=Message)
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()
    
    # Mock session for async with session.begin()
    session = AsyncMock(spec=AsyncSession)
    session.begin.return_value.__aenter__.return_value = AsyncMock()
    
    await wallet_handlers.cb_generate_wallet(callback, session, AsyncMock())
    
    # Verify the actual error message format
    call_args = callback.message.edit_text.call_args[0][0]
    assert "Unsupported chain: 'invalid'" in call_args


@pytest.mark.asyncio
@patch("bot.handlers.wallet.wallet_service.get_user_wallets", new_callable=AsyncMock)
async def test_cb_wallet_balance_refresh(mock_get: AsyncMock, session: AsyncSession):
    callback = AsyncMock(spec=CallbackQuery)
    callback.from_user = MagicMock(spec=User)
    callback.from_user.id = 123
    callback.message = AsyncMock(spec=Message)
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()
    
    mock_get.return_value = [UserWallet(chain="evm", address="0x1")]
    with patch("bot.handlers.wallet._build_balance_text", new_callable=AsyncMock) as mock_text:
        mock_text.return_value = "Balance: 100"
        await wallet_handlers.cb_wallet_balance(callback, session)
        callback.message.edit_text.assert_called()


@pytest.mark.asyncio
@patch("bot.handlers.order.order_service.get_active_orders", new_callable=AsyncMock)
async def test_cb_market_page_extra(mock_get: AsyncMock, session: AsyncSession):
    callback = AsyncMock(spec=CallbackQuery)
    callback.data = "market:page:2"
    callback.message = AsyncMock(spec=Message)
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()
    
    mock_get.return_value = {
        "orders": [Order(
            id=uuid.uuid4(), 
            asset="TON", 
            amount=Decimal("10"), 
            fiat_amount=Decimal("100"), 
            fiat_currency="RUB"
        )],
        "page": 2,
        "total_pages": 5,
        "total_count": 50
    }
    await order_handlers.cb_market_page(callback, session)
    callback.message.edit_text.assert_called()
