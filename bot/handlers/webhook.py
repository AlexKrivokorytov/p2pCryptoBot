"""Crypto Pay webhook handler — aiohttp route for /webhook/cryptopay.

Verifies HMAC-SHA256 signature, then updates order status based on
invoice state (paid → active via activate_order, expired → cancelled).
"""

from __future__ import annotations

import json

import structlog
from aiohttp import web
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from db.models.order import Order, OrderStatus
from providers.crypto_pay import CryptoPayClient
from services import order_service

log = structlog.get_logger(__name__)


async def cryptopay_webhook(request: web.Request) -> web.Response:
    """Handle incoming Crypto Pay webhook events.

    Expects:
    - Header ``crypto-pay-api-signature``: HMAC-SHA256 of raw body.
    - Body: JSON with ``payload`` (order UUID) and ``status``.

    When an invoice is paid, calls ``order_service.activate_order()`` to
    transition the order from ``pending_funding`` → ``active`` in the Order Book.

    Returns:
        200 OK on success.
        403 Forbidden on invalid signature.
        400 Bad Request on malformed payload.
    """
    crypto_pay: CryptoPayClient = request.app["crypto_pay"]
    session_pool: async_sessionmaker[AsyncSession] = request.app["session_pool"]

    # ── Signature verification — MUST happen before any payload parsing ──────────
    signature = request.headers.get("crypto-pay-api-signature", "")
    body = await request.read()

    if not crypto_pay.verify_webhook_signature(body, signature):
        log.warning(
            "webhook_hmac_failed",
            status="invalid_signature",
            ip=request.remote,
        )
        return web.Response(status=403, text="Invalid signature")

    # ── Parse body ──────────────────────────────────────────────────────────────
    try:
        data = json.loads(body)
        invoice_status: str = data["payload"]["status"]
        order_uuid: str = data["payload"]["payload"]  # our order UUID in invoice
        invoice_id: str = str(data["payload"]["invoice_id"])
    except (KeyError, ValueError, TypeError) as exc:
        log.warning(
            "webhook_invalid_payload",
            error=str(exc),
            status="bad_request",
        )
        return web.Response(status=400, text="Malformed payload")

    # ── Process event ────────────────────────────────────────────────────────────
    async with session_pool() as session:
        if invoice_status == "paid":
            # Activate the order — Maker has funded the escrow
            try:
                await order_service.activate_order(session, order_id=order_uuid)
                log.info(
                    "webhook_order_activated",
                    order_uuid=order_uuid,
                    invoice_id=invoice_id,
                    step="cryptopay_webhook",
                )
            except ValueError as exc:
                log.warning(
                    "webhook_activate_failed",
                    order_uuid=order_uuid,
                    error=str(exc),
                    step="cryptopay_webhook",
                )

        elif invoice_status == "expired":
            async with session.begin():
                result = await session.execute(
                    select(Order).where(Order.crypto_pay_payload == order_uuid).with_for_update()
                )
                order = result.scalar_one_or_none()

                if order is not None and order.status == OrderStatus.pending_funding:
                    order.status = OrderStatus.cancelled
                    log.info(
                        "webhook_order_cancelled",
                        order_id=str(order.id),
                        user_id=order.maker_id,
                        status=OrderStatus.cancelled.value,
                        step="cryptopay_webhook",
                        reason="invoice_expired",
                    )

    return web.Response(status=200, text="OK")
