"""Admin service — platform statistics and dispute queue for moderators."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.order import Order, OrderStatus

log = structlog.get_logger(__name__)


@dataclass
class PlatformStats:
    """Snapshot of key platform metrics."""

    total_orders: int
    active_orders: int
    escrow_held_orders: int
    completed_orders: int
    cancelled_orders: int
    dispute_orders: int
    pending_funding_orders: int

    # Volume (sum of fiat_amount for completed orders)
    # Stored as float because order.fiat_amount is Numeric
    total_volume_completed: float

    # Unique users (as makers or takers)
    unique_makers: int
    unique_takers: int

    generated_at: datetime


async def get_platform_stats(session: AsyncSession) -> PlatformStats:
    """Compute platform-wide statistics in a single DB round-trip per metric.

    Args:
        session: Active async SQLAlchemy session.

    Returns:
        :class:`PlatformStats` dataclass with aggregated metrics.
    """
    # Status counts via GROUP BY
    status_count_q = select(
        Order.status,
        func.count(Order.id).label("cnt"),
    ).group_by(Order.status)

    rows = (await session.execute(status_count_q)).all()
    counts: dict[str, int] = {str(row.status): int(row.cnt) for row in rows}

    total = sum(counts.values())

    # Completed volume
    volume_q = select(func.sum(Order.fiat_amount)).where(Order.status == OrderStatus.completed)
    volume_raw = (await session.execute(volume_q)).scalar()
    total_volume = float(volume_raw) if volume_raw else 0.0

    # Unique makers
    makers_q = select(func.count(func.distinct(Order.maker_id)))
    unique_makers = int((await session.execute(makers_q)).scalar() or 0)

    # Unique takers (non-null)
    takers_q = select(func.count(func.distinct(Order.taker_id))).where(Order.taker_id.is_not(None))
    unique_takers = int((await session.execute(takers_q)).scalar() or 0)

    log.info("platform_stats_computed", total_orders=total, step="get_platform_stats")

    return PlatformStats(
        total_orders=total,
        active_orders=counts.get("active", 0),
        escrow_held_orders=counts.get("escrow_held", 0),
        completed_orders=counts.get("completed", 0),
        cancelled_orders=counts.get("cancelled", 0),
        dispute_orders=counts.get("dispute", 0),
        pending_funding_orders=counts.get("pending_funding", 0),
        total_volume_completed=total_volume,
        unique_makers=unique_makers,
        unique_takers=unique_takers,
        generated_at=datetime.now(UTC),
    )


async def get_dispute_queue(session: AsyncSession, *, limit: int = 20) -> list[Order]:
    """Fetch the queue of orders currently in dispute state.

    Orders are sorted by creation date (oldest first — most urgent).

    Args:
        session: Active async SQLAlchemy session.
        limit: Maximum number of orders to return.

    Returns:
        List of :class:`~db.models.order.Order` instances in dispute.
    """
    q = (
        select(Order)
        .where(Order.status == OrderStatus.dispute)
        .order_by(Order.created_at.asc())
        .limit(limit)
    )
    result = await session.execute(q)
    orders = list(result.scalars().all())
    log.info(
        "dispute_queue_fetched",
        count=len(orders),
        step="get_dispute_queue",
    )
    return orders


async def get_orders_by_status(
    session: AsyncSession,
    status: OrderStatus,
    *,
    limit: int = 10,
) -> list[Order]:
    """Fetch orders filtered by status for admin review.

    Args:
        session: Active async SQLAlchemy session.
        status: Target :class:`~db.models.order.OrderStatus`.
        limit: Max orders to return.

    Returns:
        List of matching :class:`~db.models.order.Order` instances.
    """
    q = select(Order).where(Order.status == status).order_by(Order.created_at.desc()).limit(limit)
    result = await session.execute(q)
    return list(result.scalars().all())


def format_stats_message(stats: PlatformStats) -> str:
    """Format :class:`PlatformStats` as an HTML Telegram message.

    Args:
        stats: Platform statistics snapshot.

    Returns:
        HTML-formatted string for ``parse_mode=\"HTML\"``.
    """
    ts = stats.generated_at.strftime("%Y-%m-%d %H:%M UTC")
    return (
        "📊 <b>Platform Dashboard</b>\n"
        f"<i>Updated: {ts}</i>\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📦 <b>Orders</b>\n"
        f"  Total:        <code>{stats.total_orders}</code>\n"
        f"  🟢 Active:    <code>{stats.active_orders}</code>\n"
        f"  🔒 In escrow: <code>{stats.escrow_held_orders}</code>\n"
        f"  ✅ Completed: <code>{stats.completed_orders}</code>\n"
        f"  ❌ Cancelled: <code>{stats.cancelled_orders}</code>\n"
        f"  ⏳ Funding:   <code>{stats.pending_funding_orders}</code>\n"
        f"  ⚖️ Disputes:  <code>{stats.dispute_orders}</code>\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "💰 <b>Volume (completed)</b>\n"
        f"  Fiat total:   <code>{stats.total_volume_completed:,.2f}</code>\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "👥 <b>Users</b>\n"
        f"  Makers:  <code>{stats.unique_makers}</code>\n"
        f"  Takers:  <code>{stats.unique_takers}</code>\n"
    )


def format_dispute_order(order: Order, index: int) -> str:
    """Format a single disputed order for the admin queue list.

    Args:
        order: Disputed order instance.
        index: 1-based position in the queue.

    Returns:
        HTML-formatted string.
    """
    short_id = str(order.id)[:8]
    reason = (order.dispute_reason or "No reason provided")[:80]
    maker = getattr(order.maker, "username", None) or str(order.maker_id)
    taker = getattr(order.taker, "username", None) or str(order.taker_id) if order.taker_id else "—"
    return (
        f"<b>#{index}</b>  <code>{short_id}…</code>\n"
        f"  Asset: <b>{order.asset}</b>  Amount: <code>{float(order.amount):.6g}</code>\n"
        f"  Maker: @{maker}  Taker: @{taker}\n"
        f"  Reason: <i>{reason}</i>\n"
    )
