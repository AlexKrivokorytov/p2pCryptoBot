"""Order service — P2P deal lifecycle: create ad, activate, take, confirm, cancel."""

from __future__ import annotations

import os
import uuid
from typing import Any

import structlog
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.order import Order, OrderStatus, OrderType, SupportedAsset
from providers.crypto_pay import CryptoPayClient

log = structlog.get_logger(__name__)

# ── Config ─────────────────────────────────────────────────────────────────────
ORDER_TIMEOUT_SEC: int = int(os.environ.get("ORDER_TIMEOUT_SEC", "1800"))
ORDER_MIN_AMOUNT_USDT: float = float(os.environ.get("ORDER_MIN_AMOUNT_USDT", "1.0"))
ORDER_MAX_AMOUNT_USDT: float = float(os.environ.get("ORDER_MAX_AMOUNT_USDT", "50000.0"))
ORDERS_PER_PAGE: int = int(os.environ.get("ORDERS_PER_PAGE", "5"))


def _validate_asset(asset: str) -> None:
    """Raise ValueError if *asset* is not in the supported list."""
    try:
        SupportedAsset(asset)
    except ValueError:
        allowed = [a.value for a in SupportedAsset]
        raise ValueError(f"Unsupported asset {asset!r}. Allowed: {allowed}")


def _validate_amount(amount: float, label: str = "amount") -> None:
    """Raise ValueError if *amount* is non-positive or out of configured bounds."""
    if amount <= 0:
        raise ValueError(f"{label} must be positive, got {amount}")


async def create_order(
    session: AsyncSession,
    crypto_pay: CryptoPayClient,
    *,
    maker_id: int,
    order_type: str,
    asset: str,
    amount: float,
    fiat_currency: str,
    fiat_amount: float,
    payment_method: str = "Any",
    fee_percent: float = 0.0,
    fee_fixed: float = 0.0,
) -> dict[str, Any]:
    """Create a new P2P ad (order) and a corresponding Crypto Pay invoice.

    The Maker funds the escrow by paying the invoice. Once paid,
    the webhook calls ``activate_order`` to make the ad visible.

    Steps:
    1. Validate inputs.
    2. Insert ``Order`` with ``status=pending_funding`` inside a DB transaction.
    3. Call ``CryptoPayClient.create_invoice`` — store ``invoice_id`` + ``payment_url``.
    4. Return order summary dict with the payment link.

    Args:
        session: Active async SQLAlchemy session.
        crypto_pay: Initialised CryptoPayClient.
        maker_id: Telegram ID of the ad creator.
        order_type: "sell_crypto" or "buy_crypto".
        asset: Crypto asset ticker (must be in SupportedAsset).
        amount: Crypto amount to lock in escrow.
        fiat_currency: Fiat currency code, e.g. "RUB".
        fiat_amount: Equivalent fiat amount.
        payment_method: Fiat payment method, e.g. "Sberbank".
        fee_percent: Percentage fee (0–100).
        fee_fixed: Fixed crypto fee applied on top.

    Returns:
        Dict with ``order_id``, ``status``, ``invoice_id``, ``payment_url``.
    """
    _validate_asset(asset)
    _validate_amount(amount, "amount")
    _validate_amount(fiat_amount, "fiat_amount")

    # Validate order_type
    try:
        OrderType(order_type)
    except ValueError:
        allowed = [t.value for t in OrderType]
        raise ValueError(f"Invalid order_type {order_type!r}. Allowed: {allowed}")

    total_fee = (amount * fee_percent / 100) + fee_fixed
    spend_id = str(uuid.uuid4())

    async with session.begin():
        order = Order(
            maker_id=maker_id,
            order_type=order_type,
            asset=asset,
            amount=amount,
            fiat_amount=fiat_amount,
            fiat_currency=fiat_currency,
            payment_method=payment_method,
            status=OrderStatus.pending_funding,
            spend_id=spend_id,
            fee_percent=fee_percent,
            fee_fixed=fee_fixed,
            total_fee=total_fee,
        )
        session.add(order)
        await session.flush()  # get order.id before invoice call

        payload = str(order.id)
        invoice_data = await crypto_pay.create_invoice(asset, amount, payload)

        order.invoice_id = invoice_data["invoice_id"]
        order.crypto_pay_payload = payload
        order.payment_url = invoice_data["pay_url"]

    log.info(
        "order_created",
        user_id=maker_id,
        order_id=str(order.id),
        order_type=order_type,
        asset=asset,
        amount=amount,
        status=OrderStatus.pending_funding,
        step="create_order",
    )
    return {
        "order_id": str(order.id),
        "status": order.status,
        "invoice_id": order.invoice_id,
        "payment_url": order.payment_url,
    }


async def activate_order(
    session: AsyncSession,
    *,
    order_id: str,
) -> dict[str, Any]:
    """Activate a funded order — make it visible in the Order Book.

    Called by the webhook handler when the Maker's Crypto Pay invoice
    is confirmed as ``paid``.

    Transition: ``pending_funding`` → ``active``.

    Args:
        session: Active async SQLAlchemy session.
        order_id: UUID string of the order.

    Returns:
        Dict with ``order_id`` and ``status=active``.

    Raises:
        ValueError: If order not found or not in ``pending_funding`` status.
    """
    async with session.begin():
        result = await session.execute(
            select(Order).where(Order.id == uuid.UUID(order_id)).with_for_update()
        )
        order = result.scalar_one_or_none()
        if order is None:
            raise ValueError(f"Order {order_id!r} not found")
        if order.status != OrderStatus.pending_funding:
            raise ValueError(
                f"activate_order requires status=pending_funding, got {order.status!r}"
            )
        order.status = OrderStatus.active

    log.info(
        "order_activated",
        order_id=order_id,
        user_id=order.maker_id,
        asset=order.asset,
        amount=str(order.amount),
        status=OrderStatus.active,
        step="activate_order",
    )
    return {"order_id": order_id, "status": OrderStatus.active}


async def take_order(
    session: AsyncSession,
    *,
    order_id: str,
    taker_id: int,
) -> dict[str, Any]:
    """Accept an active order from the Order Book.

    Transition: ``active`` → ``escrow_held``.
    Uses ``with_for_update()`` to prevent two takers from grabbing
    the same order simultaneously (race condition protection).

    Args:
        session: Active async SQLAlchemy session.
        order_id: UUID string of the order.
        taker_id: Telegram ID of the user accepting the trade.

    Returns:
        Dict with ``order_id``, ``status``, and ``maker_id``.

    Raises:
        ValueError: If order not found, not active, or taker == maker.
    """
    async with session.begin():
        result = await session.execute(
            select(Order).where(Order.id == uuid.UUID(order_id)).with_for_update()
        )
        order = result.scalar_one_or_none()
        if order is None:
            raise ValueError(f"Order {order_id!r} not found")
        if order.status != OrderStatus.active:
            raise ValueError(
                f"take_order requires status=active, got {order.status!r}"
            )
        if order.maker_id == taker_id:
            raise ValueError("Cannot take your own order")

        order.taker_id = taker_id
        order.status = OrderStatus.escrow_held

    log.info(
        "order_taken",
        order_id=order_id,
        maker_id=order.maker_id,
        taker_id=taker_id,
        asset=order.asset,
        amount=str(order.amount),
        status=OrderStatus.escrow_held,
        step="take_order",
    )
    return {
        "order_id": order_id,
        "status": OrderStatus.escrow_held,
        "maker_id": order.maker_id,
    }


async def get_active_orders(
    session: AsyncSession,
    *,
    asset: str | None = None,
    fiat_currency: str | None = None,
    order_type: str | None = None,
    page: int = 1,
    page_size: int | None = None,
) -> dict[str, Any]:
    """Fetch paginated list of active orders for the Order Book.

    Args:
        session: Active async SQLAlchemy session.
        asset: Optional filter by crypto asset.
        fiat_currency: Optional filter by fiat currency.
        order_type: Optional filter by "sell_crypto" or "buy_crypto".
        page: Page number (1-indexed).
        page_size: Number of orders per page. Defaults to ORDERS_PER_PAGE.

    Returns:
        Dict with ``orders`` list, ``page``, ``total_pages``, ``total_count``.
    """
    if page_size is None:
        page_size = ORDERS_PER_PAGE

    # Build base query for active orders
    base_filter = Order.status == OrderStatus.active
    filters = [base_filter]

    if asset is not None:
        filters.append(Order.asset == asset)
    if fiat_currency is not None:
        filters.append(Order.fiat_currency == fiat_currency)
    if order_type is not None:
        filters.append(Order.order_type == order_type)

    # Count total
    count_q = select(func.count(Order.id)).where(*filters)
    total_count = (await session.execute(count_q)).scalar() or 0
    total_pages = max(1, (total_count + page_size - 1) // page_size)

    # Fetch page
    offset = (page - 1) * page_size
    data_q = (
        select(Order)
        .where(*filters)
        .order_by(Order.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    result = await session.execute(data_q)
    orders = list(result.scalars().all())

    return {
        "orders": orders,
        "page": page,
        "total_pages": total_pages,
        "total_count": total_count,
    }


async def confirm_fiat_payment(
    session: AsyncSession,
    crypto_pay: CryptoPayClient,
    *,
    order_id: str,
    moderator: bool = False,
) -> dict[str, Any]:
    """Confirm fiat payment received and release escrow to taker.

    Only valid when ``order.status == escrow_held``.
    On success → ``status=completed``.
    On transfer error → ``status=dispute``.

    For a ``sell_crypto`` order, the Maker sold crypto and receives fiat.
    The crypto is released to the Taker (the buyer).

    Args:
        session: Active async SQLAlchemy session.
        crypto_pay: Initialised CryptoPayClient.
        order_id: UUID string of the order.
        moderator: If True, skip extra checks (admin/mediator action).

    Returns:
        Dict with ``order_id`` and final ``status``.

    Raises:
        ValueError: If the order is not in the correct state.
    """
    async with session.begin():
        result = await session.execute(
            select(Order).where(Order.id == uuid.UUID(order_id)).with_for_update()
        )
        order = result.scalar_one_or_none()
        if order is None:
            raise ValueError(f"Order {order_id!r} not found")
        if order.status != OrderStatus.escrow_held:
            raise ValueError(
                f"Cannot confirm fiat for order {order_id!r} in status {order.status!r}"
            )

        # Determine recipient based on order type:
        # sell_crypto → Maker sold crypto, Taker gets the crypto
        # buy_crypto → Maker buys crypto, Maker gets the crypto
        if order.order_type == OrderType.sell_crypto:
            recipient_id = order.taker_id
        else:
            recipient_id = order.maker_id

        try:
            await crypto_pay.transfer(
                user_id=recipient_id,  # type: ignore[arg-type]
                asset=order.asset,
                amount=float(order.amount) - float(order.total_fee),
                spend_id=str(order.spend_id),
            )
            order.status = OrderStatus.completed
            order.fiat_confirmed = True
            final_status = OrderStatus.completed
        except Exception as exc:
            log.error(
                "order_transfer_failed",
                order_id=order_id,
                error=str(exc),
                step="confirm_fiat_payment",
                status="error",
            )
            order.status = OrderStatus.dispute
            final_status = OrderStatus.dispute

    log.info(
        "order_fiat_confirmed",
        order_id=order_id,
        user_id=order.maker_id,
        asset=order.asset,
        amount=str(order.amount),
        status=final_status,
        step="confirm_fiat_payment",
        moderator=moderator,
    )
    return {"order_id": order_id, "status": final_status}


async def cancel_order(
    session: AsyncSession,
    *,
    order_id: str,
    reason: str = "user_request",
) -> dict[str, Any]:
    """Cancel a pending or active order.

    Rules:
    - ``status in {pending_funding, active}`` → allowed, set ``status=cancelled``.
    - ``status=escrow_held`` → NOT allowed without mediation; raises ValueError.

    Args:
        session: Active async SQLAlchemy session.
        order_id: UUID string of the order.
        reason: Human-readable cancel reason for logs.

    Returns:
        Dict with ``order_id`` and ``status=cancelled``.

    Raises:
        ValueError: If the order cannot be cancelled in its current state.
    """
    async with session.begin():
        result = await session.execute(
            select(Order).where(Order.id == uuid.UUID(order_id)).with_for_update()
        )
        order = result.scalar_one_or_none()
        if order is None:
            raise ValueError(f"Order {order_id!r} not found")
        if order.status == OrderStatus.escrow_held:
            raise ValueError(
                f"Order {order_id!r} has funds in escrow — cancellation requires mediation"
            )
        if order.status not in {OrderStatus.pending_funding, OrderStatus.active}:
            raise ValueError(
                f"Cannot cancel order {order_id!r} in status {order.status!r}"
            )
        order.status = OrderStatus.cancelled

    log.info(
        "order_cancelled",
        order_id=order_id,
        user_id=order.maker_id,
        asset=order.asset,
        amount=str(order.amount),
        status=OrderStatus.cancelled,
        step="cancel_order",
        reason=reason,
    )
    return {"order_id": order_id, "status": OrderStatus.cancelled}
