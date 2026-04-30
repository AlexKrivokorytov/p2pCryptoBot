"""Tests for admin_service — platform stats and dispute queue."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from services import admin_service
from services.admin_service import PlatformStats, format_stats_message, format_dispute_order
from db.models.order import Order, OrderStatus
import datetime


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_stats(**kwargs: object) -> PlatformStats:
    defaults = dict(
        total_orders=100,
        active_orders=30,
        escrow_held_orders=10,
        completed_orders=50,
        cancelled_orders=8,
        dispute_orders=2,
        pending_funding_orders=0,
        total_volume_completed=1_000_000.0,
        unique_makers=40,
        unique_takers=35,
        generated_at=datetime.datetime(2026, 4, 28, 12, 0, tzinfo=datetime.timezone.utc),
    )
    defaults.update(kwargs)
    return PlatformStats(**defaults)  # type: ignore[arg-type]


# ── format_stats_message ─────────────────────────────────────────────────────

def test_format_stats_message_contains_key_fields() -> None:
    """Stats message includes orders, volume, users, and timestamp."""
    stats = _make_stats()
    text = format_stats_message(stats)

    assert "100" in text            # total_orders
    assert "30" in text             # active_orders
    assert "50" in text             # completed_orders
    assert "2" in text              # dispute_orders
    assert "1,000,000.00" in text   # total_volume_completed
    assert "40" in text             # unique_makers
    assert "35" in text             # unique_takers
    assert "2026-04-28" in text     # timestamp
    assert "Platform Dashboard" in text


def test_format_stats_message_zero_volume() -> None:
    """Zero volume displays without crash."""
    stats = _make_stats(total_volume_completed=0.0, completed_orders=0)
    text = format_stats_message(stats)
    assert "0.00" in text


# ── format_dispute_order ─────────────────────────────────────────────────────

def test_format_dispute_order_with_taker() -> None:
    """Dispute order formatting includes maker, taker, and reason."""
    order = MagicMock(spec=Order)
    order.id = "aaaaaaaa-0000-0000-0000-000000000000"
    order.asset = "BTC"
    order.amount = Decimal("0.5")
    order.maker_id = 111
    order.taker_id = 222
    order.dispute_reason = "Fiat not received"
    order.maker = MagicMock()
    order.maker.username = "alice"
    order.taker = MagicMock()
    order.taker.username = "bob"

    text = format_dispute_order(order, index=1)

    assert "#1" in text
    assert "aaaaaaaa" in text
    assert "BTC" in text
    assert "alice" in text
    assert "bob" in text
    assert "Fiat not received" in text


def test_format_dispute_order_no_taker() -> None:
    """Dispute order without taker shows dash."""
    order = MagicMock(spec=Order)
    order.id = "bbbbbbbb-0000-0000-0000-000000000000"
    order.asset = "TON"
    order.amount = Decimal("100")
    order.maker_id = 111
    order.taker_id = None
    order.dispute_reason = None
    order.maker = MagicMock()
    order.maker.username = "charlie"

    text = format_dispute_order(order, index=2)

    assert "—" in text  # no taker
    assert "No reason provided" in text


def test_format_dispute_order_long_reason_truncated() -> None:
    """Reason longer than 80 chars is truncated."""
    order = MagicMock(spec=Order)
    order.id = "cccccccc-0000-0000-0000-000000000000"
    order.asset = "ETH"
    order.amount = Decimal("1")
    order.maker_id = 999
    order.taker_id = None
    order.dispute_reason = "X" * 200
    order.maker = MagicMock()
    order.maker.username = "user"

    text = format_dispute_order(order, index=3)

    # Reason is sliced to 80 chars in formatter
    assert "X" * 81 not in text


# ── get_platform_stats ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_platform_stats_empty_db(engine) -> None:
    """Returns zeroed stats when no orders exist."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        stats = await admin_service.get_platform_stats(session)

    assert stats.total_orders == 0
    assert stats.active_orders == 0
    assert stats.completed_orders == 0
    assert stats.dispute_orders == 0
    assert stats.total_volume_completed == 0.0
    assert stats.unique_makers == 0
    assert stats.unique_takers == 0


# ── get_dispute_queue ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_dispute_queue_empty(engine) -> None:
    """Returns empty list when no disputes exist."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        orders = await admin_service.get_dispute_queue(session)

    assert orders == []


# ── get_orders_by_status ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_orders_by_status_empty(engine) -> None:
    """Returns empty list when no orders match status."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        orders = await admin_service.get_orders_by_status(session, OrderStatus.dispute)

    assert orders == []
