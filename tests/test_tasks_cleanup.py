"""Tests for background cleanup task."""

from __future__ import annotations

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
