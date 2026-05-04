"""Background cleanup task — expires pending orders past ORDER_TIMEOUT_SEC."""

from __future__ import annotations

import asyncio
import os
from datetime import timedelta

import structlog
from aiogram import Bot
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from db.models.order import Order, OrderStatus
from services import notification_service
from utils.datetime_helpers import utcnow

log = structlog.get_logger(__name__)

ORDER_TIMEOUT_SEC: int = int(os.environ.get("ORDER_TIMEOUT_SEC", "1800"))
CLEANUP_INTERVAL_SEC: int = 60  # run every minute


async def expire_pending_orders(session_pool: async_sessionmaker[AsyncSession], bot: Bot) -> int:
    """Cancel all pending orders that have exceeded ORDER_TIMEOUT_SEC.

    Returns:
        Number of orders cancelled in this run.
    """
    cutoff = utcnow() - timedelta(seconds=ORDER_TIMEOUT_SEC)
    cancelled_count = 0

    async with session_pool() as session, session.begin():
        result = await session.execute(
            select(Order)
            .where(
                Order.status == OrderStatus.pending_funding,
                Order.created_at < cutoff,
            )
            .with_for_update(skip_locked=True)
        )
        orders = result.scalars().all()

        for order in orders:
            order.status = OrderStatus.cancelled
            cancelled_count += 1
            log.info(
                "order_expired",
                order_id=str(order.id),
                user_id=order.maker_id,
                asset=order.asset,
                amount=str(order.amount),
                status=OrderStatus.cancelled.value,
                step="cleanup_task",
                reason="timeout",
            )
            # Notify the maker
            await notification_service.notify_order_expired(
                bot, order.maker_id, str(order.id), order.asset
            )

    return cancelled_count


async def start_cleanup_task(session_pool: async_sessionmaker[AsyncSession], bot: Bot) -> None:
    """Run the cleanup loop indefinitely, every CLEANUP_INTERVAL_SEC seconds."""
    log.info("cleanup_task_started", interval_sec=CLEANUP_INTERVAL_SEC)
    while True:
        try:
            count = await expire_pending_orders(session_pool, bot)
            if count:
                log.info("cleanup_cycle_done", cancelled=count)
        except asyncio.CancelledError:
            log.info("cleanup_task_stopped")
            break
        except Exception as exc:
            log.error("cleanup_task_error", error=str(exc))
        await asyncio.sleep(CLEANUP_INTERVAL_SEC)
