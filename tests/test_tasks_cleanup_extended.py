"""Tests for cleanup task — full coverage of start_cleanup_task loop."""

from __future__ import annotations

import asyncio
import contextlib
import os
import uuid
from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from db.models.order import Order, OrderStatus, OrderType
from db.models.user import User
from tasks import cleanup
from utils.datetime_helpers import utcnow

pytestmark = pytest.mark.unit

# ── Helpers ────────────────────────────────────────────────────────────────────


async def _create_expired_order(
    session: AsyncSession, maker_id: int, status: OrderStatus, offset_sec: int
) -> Order:
    async with session.begin():
        existing = await session.get(User, maker_id)
        if not existing:
            session.add(User(telegram_id=maker_id, username=f"user_{maker_id}", first_name="T"))
        order = Order(
            maker_id=maker_id,
            order_type=OrderType.sell_crypto,
            asset="BTC",
            amount=0.1,
            fiat_currency="USD",
            fiat_amount=100.0,
            payment_method="Sberbank",
            status=status,
            spend_id=str(uuid.uuid4()),
        )
        order.created_at = utcnow() + timedelta(seconds=offset_sec)
        session.add(order)
        return order


# ── start_cleanup_task ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_start_cleanup_task_cancels_cleanly(engine) -> None:
    """start_cleanup_task stops gracefully on CancelledError."""
    factory = async_sessionmaker(engine, expire_on_commit=False)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    task = asyncio.create_task(cleanup.start_cleanup_task(factory, bot=AsyncMock()))
    await asyncio.sleep(0.05)
    task.cancel()

    with contextlib.suppress(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_start_cleanup_task_handles_exception(engine) -> None:
    """start_cleanup_task logs errors but keeps running on unexpected exceptions."""
    factory = async_sessionmaker(engine, expire_on_commit=False)
    call_count = 0

    async def failing_expire(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("DB temporarily down")
        return 0

    with (
        patch.object(cleanup, "expire_pending_orders", side_effect=failing_expire),
        patch.object(cleanup, "CLEANUP_INTERVAL_SEC", 0),
    ):
        task = asyncio.create_task(cleanup.start_cleanup_task(factory, bot=AsyncMock()))
        await asyncio.sleep(0.1)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    assert call_count >= 2, "Should have retried after the error"


@pytest.mark.asyncio
async def test_start_cleanup_task_logs_when_orders_cancelled(engine) -> None:
    """start_cleanup_task logs cancelled count when orders are expired."""
    factory = async_sessionmaker(engine, expire_on_commit=False)
    timeout = int(os.environ.get("ORDER_TIMEOUT_SEC", "1800"))

    # Create an expired pending_funding order
    async with factory() as session:
        await _create_expired_order(
            session, maker_id=401, status=OrderStatus.pending_funding, offset_sec=-(timeout + 200)
        )

    cancelled_counts = []

    original_expire = cleanup.expire_pending_orders

    async def tracking_expire(*args, **kwargs):
        count = await original_expire(*args, **kwargs)
        cancelled_counts.append(count)
        return count

    with (
        patch.object(cleanup, "expire_pending_orders", side_effect=tracking_expire),
        patch.object(cleanup, "CLEANUP_INTERVAL_SEC", 0),
    ):
        task = asyncio.create_task(cleanup.start_cleanup_task(factory, bot=AsyncMock()))
        await asyncio.sleep(0.2)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    assert any(c > 0 for c in cancelled_counts), "Expected at least one cancellation"
