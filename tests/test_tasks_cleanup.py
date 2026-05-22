"""Tests for background cleanup task."""

from __future__ import annotations

import asyncio
import contextlib
import os
import uuid
from datetime import timedelta
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from db.models.order import Order, OrderStatus, OrderType
from db.models.user import User
from tasks import cleanup
from utils.datetime_helpers import utcnow

pytestmark = pytest.mark.unit


async def _create_order(session: AsyncSession, status: OrderStatus, offset_seconds: int) -> Order:
    user = User(telegram_id=301, username="cleanup_test")

    order = Order(
        maker_id=301,
        order_type=OrderType.sell_crypto,
        asset="BTC",
        amount=1.0,
        fiat_currency="RUB",
        fiat_amount=100.0,
        payment_method="Sberbank",
        status=status,
        spend_id=str(uuid.uuid4()),
    )
    # Manually set created_at for testing
    order.created_at = utcnow() + timedelta(seconds=offset_seconds)
    async with session.begin():
        db_user = await session.get(User, 301)
        if not db_user:
            session.add(user)
        session.add(order)
    return order


@pytest.mark.integration
@pytest.mark.asyncio
async def test_expire_pending_orders(engine) -> None:
    """Old pending_funding orders should be cancelled, others left alone."""
    factory = async_sessionmaker(engine, expire_on_commit=False)
    timeout = int(os.environ.get("ORDER_TIMEOUT_SEC", "1800"))

    async with factory() as session:
        o1 = await _create_order(
            session, OrderStatus.pending_funding, offset_seconds=-(timeout + 100)
        )  # should cancel
        o2 = await _create_order(
            session, OrderStatus.pending_funding, offset_seconds=-10
        )  # should NOT cancel (too new)
        o3 = await _create_order(
            session, OrderStatus.escrow_held, offset_seconds=-(timeout + 100)
        )  # should NOT cancel (wrong status)

        o1_id, o2_id, o3_id = o1.id, o2.id, o3.id

    # Run cleanup
    count = await cleanup.expire_pending_orders(factory, bot=AsyncMock())
    assert count == 1

    # Verify state
    async with factory() as session:
        db_o1 = await session.scalar(select(Order).where(Order.id == o1_id))
        db_o2 = await session.scalar(select(Order).where(Order.id == o2_id))
        db_o3 = await session.scalar(select(Order).where(Order.id == o3_id))

        assert db_o1.status == OrderStatus.cancelled
        assert db_o2.status == OrderStatus.pending_funding
        assert db_o3.status == OrderStatus.escrow_held

        # Cleanup test data
        await session.delete(db_o1)
        await session.delete(db_o2)
        await session.delete(db_o3)
        await session.commit()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_start_cleanup_task_cancels_cleanly(engine) -> None:
    """start_cleanup_task stops gracefully on CancelledError."""
    from aiogram import Bot

    from providers.crypto_pay import CryptoPayClient

    factory = async_sessionmaker(engine, expire_on_commit=False)

    task = asyncio.create_task(
        cleanup.start_cleanup_task(
            factory, bot=AsyncMock(spec=Bot), crypto_pay=AsyncMock(spec=CryptoPayClient)
        )
    )
    await asyncio.sleep(0.05)
    task.cancel()

    with contextlib.suppress(asyncio.CancelledError):
        await task


@pytest.mark.integration
@pytest.mark.asyncio
async def test_start_cleanup_task_handles_exception(engine) -> None:
    """start_cleanup_task logs errors but keeps running on unexpected exceptions."""
    from unittest.mock import patch

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
        task = asyncio.create_task(
            cleanup.start_cleanup_task(factory, bot=AsyncMock(), crypto_pay=AsyncMock())
        )

        await asyncio.sleep(0.1)
        task.cancel()

        with contextlib.suppress(asyncio.CancelledError):
            await task

    assert call_count >= 2, "Should have retried after the error"
