"""
Contract tests — verify database layer handles concurrent financial operations correctly.

These tests verify properties that matter to buyers of this white-label product:

1. Concurrent take_order calls — only one taker wins (race condition protection)
2. Status transitions are sequential and validated
3. Pessimistic locking (SELECT ... FOR UPDATE) actually prevents double-spending
4. Self-dealing is rejected at the service layer

These are *integration* tests — they require a real PostgreSQL database.
The 'engine' and 'session' fixtures are provided by conftest.py.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from db.models.order import Order, OrderStatus, OrderType
from db.models.user import User
from services import order_service

# ── Seed helpers ───────────────────────────────────────────────────────────────


async def _seed_user(session: AsyncSession, telegram_id: int, username: str) -> None:
    """Insert a User row if it does not already exist."""
    from sqlalchemy import select

    exists = await session.scalar(select(User).where(User.telegram_id == telegram_id))
    if exists is None:
        session.add(User(telegram_id=telegram_id, username=username, first_name="Test"))
        await session.flush()


async def _seed_active_order(
    factory: async_sessionmaker,  # type: ignore[type-arg]
    maker_id: int,
) -> str:
    """Create a User and an active Order in the database, return the order UUID string."""
    async with factory() as s, s.begin():
        await _seed_user(s, maker_id, f"maker_{maker_id}")
        order = Order(
            maker_id=maker_id,
            order_type=OrderType.sell_crypto,
            asset="USDT",
            amount=10.0,
            fiat_currency="USD",
            fiat_amount=100.0,
            payment_method="Bank",
            status=OrderStatus.active,
            spend_id=str(uuid.uuid4()),
        )
        s.add(order)
        await s.flush()
        return str(order.id)


@pytest_asyncio.fixture
async def db_factory(engine):  # type: ignore[no-untyped-def]
    """Return an async_sessionmaker bound to the test engine (NullPool-safe)."""
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


# ── Test: Concurrent take_order ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_concurrent_take_order_exactly_one_wins(db_factory) -> None:  # type: ignore[no-untyped-def]
    """Pessimistic locking must ensure only one taker can claim an active order.

    Three buyers fire simultaneously. The DB lock (SELECT ... FOR UPDATE)
    guarantees exactly one transaction commits. The other two must receive
    ValueError (order not active), proving no double-spending is possible.
    """
    order_id = await _seed_active_order(db_factory, maker_id=80001)

    # Seed three competing takers
    async with db_factory() as s, s.begin():
        for uid, name in [(80002, "taker_a"), (80003, "taker_b"), (80004, "taker_c")]:
            await _seed_user(s, uid, name)

    results: list[tuple[str, object]] = []

    async def try_take(taker_id: int) -> None:
        async with db_factory() as s:
            try:
                await order_service.take_order(s, order_id=order_id, taker_id=taker_id)
                results.append(("ok", taker_id))
            except ValueError as exc:
                results.append(("err", str(exc)))

    await asyncio.gather(try_take(80002), try_take(80003), try_take(80004))

    successes = [r for r in results if r[0] == "ok"]
    assert len(successes) == 1, (
        f"Expected exactly 1 winner in concurrent race, got {len(successes)}: {results}"
    )
    errors = [r for r in results if r[0] == "err"]
    assert len(errors) == 2, (
        f"Expected exactly 2 losers in concurrent race, got {len(errors)}: {results}"
    )


# ── Test: Invalid status transition ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_activate_order_rejects_non_pending_status(db_factory) -> None:  # type: ignore[no-untyped-def]
    """activate_order must raise ValueError if order is not in pending_funding state.

    We seed an ACTIVE order and try to activate it again. This would be
    a replay attack — it must be rejected.
    """
    order_id = await _seed_active_order(db_factory, maker_id=80010)

    async with db_factory() as s:
        with pytest.raises(ValueError, match="activate_order requires status=pending_funding"):
            await order_service.activate_order(s, order_id=order_id)


# ── Test: Self-dealing prevention ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_self_take_prevented_by_service(db_factory) -> None:  # type: ignore[no-untyped-def]
    """A maker must not be able to take their own order.

    This is a fundamental P2P security constraint. If violated, a single
    user could fraudulently collect escrow from themselves.
    """
    maker_id = 80020
    order_id = await _seed_active_order(db_factory, maker_id=maker_id)

    async with db_factory() as s:
        with pytest.raises(ValueError, match="Cannot take your own order"):
            await order_service.take_order(s, order_id=order_id, taker_id=maker_id)


# ── Test: Take non-existent order ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_take_nonexistent_order_raises(db_factory) -> None:  # type: ignore[no-untyped-def]
    """Attempting to take an order that doesn't exist must raise ValueError."""
    fake_order_id = str(uuid.uuid4())

    async with db_factory() as s:
        with pytest.raises(ValueError, match="not found"):
            await order_service.take_order(s, order_id=fake_order_id, taker_id=99999)


# ── Test: Sequential status transitions ────────────────────────────────────────


@pytest.mark.asyncio
async def test_order_status_is_escrow_held_after_take(db_factory) -> None:  # type: ignore[no-untyped-def]
    """After a successful take_order, the order status must be escrow_held."""
    maker_id = 80030
    taker_id = 80031
    order_id = await _seed_active_order(db_factory, maker_id=maker_id)

    async with db_factory() as s, s.begin():
        await _seed_user(s, taker_id, "taker_80031")

    async with db_factory() as s:
        result = await order_service.take_order(s, order_id=order_id, taker_id=taker_id)

    assert result["status"] == OrderStatus.escrow_held
    assert result["order_id"] == order_id
    assert result["maker_id"] == maker_id


@pytest.mark.asyncio
async def test_double_take_rejected_after_first_success(db_factory) -> None:  # type: ignore[no-untyped-def]
    """A second take_order call on an already-claimed order must fail.

    After the first taker claims it (status = escrow_held), the order
    is no longer active. A second take attempt must raise ValueError.
    """
    maker_id = 80040
    taker_a_id = 80041
    taker_b_id = 80042
    order_id = await _seed_active_order(db_factory, maker_id=maker_id)

    async with db_factory() as s, s.begin():
        await _seed_user(s, taker_a_id, "taker_80041")
        await _seed_user(s, taker_b_id, "taker_80042")

    # First taker wins
    async with db_factory() as s:
        result = await order_service.take_order(s, order_id=order_id, taker_id=taker_a_id)
    assert result["status"] == OrderStatus.escrow_held

    # Second taker must be rejected
    async with db_factory() as s:
        with pytest.raises(ValueError, match="take_order requires status=active"):
            await order_service.take_order(s, order_id=order_id, taker_id=taker_b_id)
