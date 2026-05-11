"""Dispute service — raise and resolve P2P order disputes."""

from __future__ import annotations

import uuid
from typing import Any

import structlog
from aiogram import Bot
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.order import Order, OrderStatus
from providers.crypto_pay import CryptoPayClient
from services import escrow_service, notification_service, order_service

log = structlog.get_logger(__name__)

# Decisions accepted by resolve_dispute
VALID_DECISIONS: frozenset[str] = frozenset({"taker_wins", "maker_wins", "cancel"})


async def raise_dispute(
    session: AsyncSession,
    *,
    order_id: str,
    reason: str,
    raised_by: int,
) -> dict[str, Any]:
    """Raise a dispute on an active order.

    Transitions ``active`` or ``escrow_held`` → ``dispute``.
    Locks the order against any further normal-user status changes.

    Args:
        session: Active async SQLAlchemy session.
        order_id: UUID string of the order.
        reason: Human-readable reason for the dispute.
        raised_by: Telegram user ID of the party raising the dispute.

    Returns:
        Dict with ``order_id`` and ``status=dispute``.

    Raises:
        ValueError: If the order cannot be disputed in its current state.
    """
    async with session.begin():
        result = await session.execute(
            select(Order).where(Order.id == uuid.UUID(order_id)).with_for_update()
        )
        order = result.scalar_one_or_none()
        if order is None:
            raise ValueError(f"Order {order_id!r} not found")
        if order.status not in {OrderStatus.active, OrderStatus.escrow_held}:
            raise ValueError(f"Cannot raise dispute on order in status {order.status!r}")
        order.status = OrderStatus.dispute
        order.dispute_reason = reason

    log.info(
        "dispute_raised",
        order_id=order_id,
        user_id=raised_by,
        reason=reason,
        status=OrderStatus.dispute,
        step="raise_dispute",
    )
    return {"order_id": order_id, "status": OrderStatus.dispute}


async def resolve_dispute(
    session: AsyncSession,
    crypto_pay: CryptoPayClient,
    bot: Bot,
    *,
    order_id: str,
    decision: str,
    moderator_id: int,
) -> dict[str, Any]:
    """Resolve a disputed order by moderator decision.

    Decisions:
    - ``taker_wins`` → release escrow to taker (crypto goes to them).
    - ``maker_wins`` → refund escrow back to maker.
    - ``cancel`` → refund to maker.

    Args:
        session: Active async SQLAlchemy session.
        crypto_pay: Initialised CryptoPayClient.
        bot: Bot instance for notifications.
        order_id: UUID string of the order.
        decision: One of ``taker_wins``, ``maker_wins``, ``cancel``.
        moderator_id: Telegram ID of the resolving moderator.

    Returns:
        Dict with ``order_id``, final ``status``, and ``decision``.

    Raises:
        ValueError: If decision is invalid or order is not in dispute.
    """
    if decision not in VALID_DECISIONS:
        raise ValueError(f"Invalid decision {decision!r}. Must be one of {VALID_DECISIONS}")

    # Fetch order details before resolution for notifications
    order_data = await order_service.get_order_details(session, order_id=order_id)
    if not order_data:
        raise ValueError(f"Order {order_id!r} not found")

    # Execute the appropriate escrow action.
    if decision == "taker_wins":
        result_data = await escrow_service.release_escrow(
            session, crypto_pay, order_id=order_id, force=True, require_dispute=True
        )
    else:
        # maker_wins or cancel both refund to maker
        result_data = await escrow_service.refund_escrow(
            session, crypto_pay, order_id=order_id, force=True, require_dispute=True
        )

    # Notify both parties
    await notification_service.notify_dispute_resolved(
        bot,
        maker_id=order_data["maker_id"],
        taker_id=order_data["taker_id"],
        order_id=order_id,
        decision=decision,
        status=str(result_data["status"]),
    )

    log.info(
        "dispute_resolved",
        order_id=order_id,
        moderator_id=moderator_id,
        decision=decision,
        final_status=result_data["status"],
        step="resolve_dispute",
        status="ok",
    )
    return {"order_id": order_id, "status": result_data["status"], "decision": decision}
