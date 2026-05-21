"""Background cleanup task — expires pending orders and stagnant trades."""

from __future__ import annotations

import asyncio
import os
from datetime import timedelta

import structlog
from aiogram import Bot
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from db.models.order import Order, OrderStatus
from providers.crypto_pay import CryptoPayClient
from services import escrow_service, notification_service, order_service
from utils.datetime_helpers import utcnow

log = structlog.get_logger(__name__)

ORDER_TIMEOUT_SEC: int = int(os.environ.get("ORDER_TIMEOUT_SEC", "1800"))
TRADE_TIMEOUT_SEC: int = int(os.environ.get("TRADE_TIMEOUT_SEC", "1800"))
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
                reason="timeout_pending",
            )
            # Notify the maker
            await notification_service.notify_order_expired(
                bot, order.maker_id, str(order.id), order.asset
            )

    return cancelled_count


async def expire_stagnant_trades(
    session_pool: async_sessionmaker[AsyncSession], bot: Bot, crypto_pay: CryptoPayClient
) -> int:
    """Cancel and refund escrow_held trades where no fiat was confirmed within TRADE_TIMEOUT_SEC.

    Returns:
        Number of trades expired.
    """
    cutoff = utcnow() - timedelta(seconds=TRADE_TIMEOUT_SEC)
    expired_count = 0

    async with session_pool() as session:
        # We process each order separately to avoid holding locks too long
        result = await session.execute(
            select(Order).where(
                Order.status == OrderStatus.escrow_held,
                Order.fiat_confirmed == False,  # noqa: E712
                Order.updated_at < cutoff,
            )
        )
        orders = result.scalars().all()

        for order in orders:
            try:
                # Fetch order details for notification data
                order_data = await order_service.get_order_details(session, order_id=str(order.id))

                # Use escrow_service.refund_escrow which handles locking and stats
                await escrow_service.refund_escrow(
                    session,
                    crypto_pay,
                    order_id=str(order.id),
                    force=True,
                )
                expired_count += 1
                log.info(
                    "trade_expired",
                    order_id=str(order.id),
                    maker_id=order.maker_id,
                    taker_id=order.taker_id,
                    step="cleanup_task",
                    reason="timeout_escrow",
                )
                # Notify Maker about refund
                if order_data:
                    await notification_service.notify_escrow_refunded(
                        bot, order.maker_id, str(order.id), order.asset, order_data["amount"]
                    )
                # Notify Taker about cancellation
                if order.taker_id:
                    await notification_service.notify_order_expired(
                        bot, order.taker_id, str(order.id), order.asset
                    )
            except Exception as e:
                log.error("trade_expiry_failed", order_id=str(order.id), error=str(e))

    return expired_count


async def verify_top_sellers(session_pool: async_sessionmaker[AsyncSession]) -> int:
    """Auto-verify sellers who meet performance criteria."""
    verified_count = 0
    async with session_pool() as session, session.begin():
        from db.models.user import User
        result = await session.execute(
            select(User).where(
                User.is_verified_seller.is_(False),
                User.successful_trades >= 10,
                User.review_count >= 5,
            )
        )
        users = result.scalars().all()
        for u in users:
            if u.review_count and (float(u.rating_sum) / float(u.review_count)) >= 4.5:
                u.is_verified_seller = True
                verified_count += 1
                log.info("seller_auto_verified", user_id=u.telegram_id, step="cleanup_task")
    return verified_count


async def start_cleanup_task(
    session_pool: async_sessionmaker[AsyncSession], bot: Bot, crypto_pay: CryptoPayClient
) -> None:
    """Run the cleanup loop indefinitely, every CLEANUP_INTERVAL_SEC seconds."""
    log.info("cleanup_task_started", interval_sec=CLEANUP_INTERVAL_SEC)
    while True:
        try:
            # 1. Expire ads that were never funded
            pending_count = await expire_pending_orders(session_pool, bot)

            # 2. Expire trades that were accepted but never paid
            stagnant_count = await expire_stagnant_trades(session_pool, bot, crypto_pay)
            
            # 3. Auto-verify top sellers
            verified_count = await verify_top_sellers(session_pool)

            if pending_count or stagnant_count or verified_count:
                log.info("cleanup_cycle_done", pending=pending_count, stagnant=stagnant_count, verified=verified_count)
        except asyncio.CancelledError:
            log.info("cleanup_task_stopped")
            break
        except Exception as exc:
            log.error("cleanup_task_error", error=str(exc))
        await asyncio.sleep(CLEANUP_INTERVAL_SEC)
