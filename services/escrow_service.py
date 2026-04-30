"""Escrow service — release and refund crypto funds for P2P orders.

Note: ``hold_escrow`` was removed in the Maker/Taker refactor.
Escrow is now funded via the Maker paying the Crypto Pay invoice,
and ``activate_order()`` handles the ``pending_funding → active`` transition.
"""

from __future__ import annotations

import uuid
from datetime import datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.order import Order, OrderStatus, OrderType
from providers.crypto_pay import CryptoPayClient
from services import user_service

log = structlog.get_logger(__name__)


async def release_escrow(
    session: AsyncSession,
    crypto_pay: CryptoPayClient,
    *,
    order_id: str,
    force: bool = False,
) -> dict[str, object]:
    """Release escrowed funds to the appropriate recipient.

    For ``sell_crypto``: crypto goes to the **Taker** (they bought crypto).
    For ``buy_crypto``: crypto goes to the **Maker** (they wanted to buy crypto).

    Requires ``status=escrow_held`` and ``fiat_confirmed=True``,
    unless *force=True* (admin/mediator action from dispute status).

    Args:
        session: Active async SQLAlchemy session.
        crypto_pay: Initialised CryptoPayClient.
        order_id: UUID string of the order.
        force: Bypass fiat_confirmed check (moderator only).

    Returns:
        Dict with ``order_id`` and ``status=completed``.

    Raises:
        ValueError: If order state does not allow release.
    """
    async with session.begin():
        result = await session.execute(
            select(Order).where(Order.id == uuid.UUID(order_id)).with_for_update()
        )
        order = result.scalar_one_or_none()
        if order is None:
            raise ValueError(f"Order {order_id!r} not found")
        allowed_statuses = {OrderStatus.escrow_held}
        if force:
            allowed_statuses.add(OrderStatus.dispute)
        if order.status not in allowed_statuses:
            raise ValueError(
                f"release_escrow requires status in {allowed_statuses}, got {order.status!r}"
            )
        if not force and not order.fiat_confirmed:
            raise ValueError("Fiat payment not yet confirmed for this order")

        # Determine recipient based on order type
        if order.order_type == OrderType.sell_crypto:
            recipient_id = order.taker_id
        else:
            recipient_id = order.maker_id

        await crypto_pay.transfer(
            user_id=recipient_id,
            asset=order.asset,
            amount=float(order.amount) - float(order.total_fee),
            spend_id=str(order.spend_id),
        )
        # Mark order as completed
        order.status = OrderStatus.completed
        order.updated_at = datetime.utcnow()
        session.add(order)

        # Increment stats
        await user_service.increment_user_trade_stats(session, order.maker_id, successful=True)
        if order.taker_id:
            await user_service.increment_user_trade_stats(session, order.taker_id, successful=True)

    log.info(
        "escrow_released",
        order_id=order_id,
        recipient_id=recipient_id,
        asset=order.asset,
        amount=str(order.amount),
        status=OrderStatus.completed,
        step="release_escrow",
        force=force,
    )
    return {"order_id": order_id, "status": OrderStatus.completed}


async def refund_escrow(
    session: AsyncSession,
    crypto_pay: CryptoPayClient,
    *,
    order_id: str,
    force: bool = False,
) -> dict[str, object]:
    """Refund escrowed funds back to the Maker (the person who funded them).

    Only available via admin/mediator (force=True) or system-driven policy.

    Args:
        session: Active async SQLAlchemy session.
        crypto_pay: Initialised CryptoPayClient.
        order_id: UUID string of the order.
        force: Must be True (guards against accidental calls).

    Returns:
        Dict with ``order_id`` and ``status=cancelled``.

    Raises:
        ValueError: If force is False or order state is invalid.
    """
    if not force:
        raise ValueError("refund_escrow requires force=True (admin/mediator only)")

    async with session.begin():
        result = await session.execute(
            select(Order).where(Order.id == uuid.UUID(order_id)).with_for_update()
        )
        order = result.scalar_one_or_none()
        if order is None:
            raise ValueError(f"Order {order_id!r} not found")
        if order.status not in {OrderStatus.escrow_held, OrderStatus.dispute}:
            raise ValueError(f"refund_escrow invalid for status {order.status!r}")

        # Refund always goes back to the Maker (they funded the escrow)
        await crypto_pay.transfer(
            user_id=order.maker_id,
            asset=order.asset,
            amount=float(order.amount),
            spend_id=f"refund-{order.spend_id}",
        )
        order.status = OrderStatus.cancelled

        # Increment stats (unsuccessful)
        await user_service.increment_user_trade_stats(session, order.maker_id, successful=False)
        if order.taker_id:
            await user_service.increment_user_trade_stats(session, order.taker_id, successful=False)

    log.info(
        "escrow_refunded",
        order_id=order_id,
        user_id=order.maker_id,
        asset=order.asset,
        amount=str(order.amount),
        status=OrderStatus.cancelled,
        step="refund_escrow",
        force=force,
    )
    return {"order_id": order_id, "status": OrderStatus.cancelled}
