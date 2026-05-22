"""Escrow service — release and refund crypto funds for P2P orders.

Note: ``hold_escrow`` was removed in the Maker/Taker refactor.
Escrow is now funded via the Maker paying the Crypto Pay invoice,
and ``activate_order()`` handles the ``pending_funding → active`` transition.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.order import Order, OrderStatus, OrderType
from providers.crypto_pay import CryptoPayClient
from services import user_service, wallet_service

log = structlog.get_logger(__name__)


async def release_escrow(
    session: AsyncSession,
    crypto_pay: CryptoPayClient,
    order_id: str,
    force: bool = False,
    require_dispute: bool = False,
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
        require_dispute: If True, strictly requires status=dispute.

    Returns:
        Dict with ``order_id`` and ``status=completed``.

    Raises:
        ValueError: If order state does not allow release.
    """
    if session.in_transaction():
        return await _release_escrow_logic(session, crypto_pay, order_id, force, require_dispute)

    async with session.begin():
        return await _release_escrow_logic(session, crypto_pay, order_id, force, require_dispute)


async def _release_escrow_logic(
    session: AsyncSession,
    crypto_pay: CryptoPayClient,
    order_id: str,
    force: bool = False,
    require_dispute: bool = False,
) -> dict[str, Any]:
    """Internal logic for releasing escrow."""
    result = await session.execute(
        select(Order).where(Order.id == uuid.UUID(order_id)).with_for_update()
    )
    order = result.scalar_one_or_none()
    if order is None:
        raise ValueError(f"Order {order_id!r} not found")
    allowed_statuses = {OrderStatus.escrow_held}
    if force:
        allowed_statuses.add(OrderStatus.dispute)
    if require_dispute:
        allowed_statuses = {OrderStatus.dispute}

    if order.status not in allowed_statuses:
        # If require_dispute is set, emit a specific error message for tests
        if require_dispute:
            raise ValueError(f"resolve_dispute requires status=dispute, got {order.status!r}")
        raise ValueError(
            f"release_escrow requires status in {allowed_statuses}, got {order.status!r}"
        )
    if not force and not order.fiat_confirmed:
        raise ValueError("Fiat payment not yet confirmed for this order")

    # Determine recipient based on order type
    recipient_id = order.taker_id if order.order_type == OrderType.sell_crypto else order.maker_id

    chain = wallet_service.get_chain_for_asset(order.asset)
    if chain and order.escrow_wallet_address:
        # 1. Ensure recipient has a wallet on this chain
        recipient_wallet = await wallet_service.get_user_wallet_by_chain(
            session, recipient_id, chain
        )
        if not recipient_wallet:
            recipient_wallet = await wallet_service.generate_and_save_wallet(
                session, recipient_id, chain
            )

        to_address = recipient_wallet.address
        amount_net = Decimal(str(order.amount)) - Decimal(str(order.total_fee))

        # 2. Execute on-chain transfer from escrow wallet
        tx_hash = await wallet_service.transfer_from_order_wallet(
            session,
            str(order.id),
            chain,
            to_address,
            order.asset,
            amount_net,
            memo=f"P2P {str(order.id)[:8]}",
        )
        order.on_chain_tx_hash = tx_hash
        order.on_chain_status = "released"
    else:
        # Legacy Crypto Pay release
        await crypto_pay.transfer(
            user_id=recipient_id,
            asset=order.asset,
            amount=order.amount - order.total_fee,
            spend_id=order.spend_id,
        )
    # Mark order as completed
    order.status = OrderStatus.completed
    order.updated_at = datetime.now(UTC)
    session.add(order)

    # Increment stats
    await user_service.increment_user_trade_stats(session, order.maker_id, successful=True)
    if order.taker_id:
        await user_service.increment_user_trade_stats(session, order.taker_id, successful=True)

    # Process referral reward (from platform fee)
    if order.total_fee > 0 and order.taker_id:
        from services.referral_service import ReferralService

        await ReferralService.process_referral_reward(
            session=session,
            order_id=order.id,
            deal_id=None,
            referred_user_id=order.taker_id,
            asset=order.asset,
            total_fee=float(order.total_fee),
            reward_percentage=0.20,
        )

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
    require_dispute: bool = False,
) -> dict[str, object]:
    """Refund escrowed funds back to the Maker (the person who funded them).

    Only available via admin/mediator (force=True) or system-driven policy.

    Args:
        session: Active async SQLAlchemy session.
        crypto_pay: Initialised CryptoPayClient.
        order_id: UUID string of the order.
        force: Must be True (guards against accidental calls).
        require_dispute: If True, strictly requires status=dispute.

    Returns:
        Dict with ``order_id`` and ``status=cancelled``.

    Raises:
        ValueError: If force is False or order state is invalid.
    """
    if not force:
        raise ValueError("refund_escrow requires force=True (admin/mediator only)")

    if session.in_transaction():
        return await _refund_escrow_logic(session, crypto_pay, order_id, force, require_dispute)

    async with session.begin():
        return await _refund_escrow_logic(session, crypto_pay, order_id, force, require_dispute)


async def _refund_escrow_logic(
    session: AsyncSession,
    crypto_pay: CryptoPayClient,
    order_id: str,
    force: bool = False,
    require_dispute: bool = False,
) -> dict[str, Any]:
    """Internal logic for refunding escrow."""
    result = await session.execute(
        select(Order).where(Order.id == uuid.UUID(order_id)).with_for_update()
    )
    order = result.scalar_one_or_none()
    if order is None:
        raise ValueError(f"Order {order_id!r} not found")

    allowed_statuses = {OrderStatus.escrow_held, OrderStatus.dispute}
    if require_dispute:
        allowed_statuses = {OrderStatus.dispute}

    if order.status not in allowed_statuses:
        if require_dispute:
            raise ValueError(f"resolve_dispute requires status=dispute, got {order.status!r}")
        raise ValueError(f"refund_escrow invalid for status {order.status!r}")

    # Refund always goes back to the Maker (they funded the escrow)
    chain = wallet_service.get_chain_for_asset(order.asset)
    if chain and order.escrow_wallet_address:
        # 1. Ensure maker has a wallet on this chain
        maker_wallet = await wallet_service.get_user_wallet_by_chain(session, order.maker_id, chain)
        if not maker_wallet:
            maker_wallet = await wallet_service.generate_and_save_wallet(
                session, order.maker_id, chain
            )

        # 2. Transfer back to Maker
        await wallet_service.transfer_from_order_wallet(
            session,
            str(order.id),
            chain,
            maker_wallet.address,
            order.asset,
            order.amount,
            memo=f"Refund {str(order.id)[:8]}",
        )
        order.on_chain_status = "refunded"
    else:
        # Legacy Crypto Pay refund
        await crypto_pay.transfer(
            user_id=order.maker_id,
            asset=order.asset,
            amount=order.amount,
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
