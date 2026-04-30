"""Dispute service — raise, resolve, and AI-mediate P2P order disputes."""

from __future__ import annotations

import os
import uuid
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.order import Order, OrderStatus
from providers.crypto_pay import CryptoPayClient
from services import escrow_service

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

    # Validate order is in dispute state first (read-only check)
    async with session.begin():
        result = await session.execute(select(Order).where(Order.id == uuid.UUID(order_id)))
        order = result.scalar_one_or_none()
        if order is None:
            raise ValueError(f"Order {order_id!r} not found")
        if order.status != OrderStatus.dispute:
            raise ValueError(f"resolve_dispute requires status=dispute, got {order.status!r}")

    # Execute the appropriate escrow action
    if decision == "taker_wins":
        result_data = await escrow_service.release_escrow(
            session, crypto_pay, order_id=order_id, force=True
        )
    else:
        # maker_wins or cancel both refund to maker
        result_data = await escrow_service.refund_escrow(
            session, crypto_pay, order_id=order_id, force=True
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


async def ai_mediator_suggest(
    order_id: str,
    chat_history: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Ask the Gemini AI mediator to suggest dispute resolution terms.

    Reads the order details (and optionally the conversation history between
    maker and taker) and returns a suggested decision with reasoning.

    Args:
        order_id: UUID string of the order.
        chat_history: Optional list of ``{"role": "maker"|"taker", "text": "..."}``
                      messages from the order chat.

    Returns:
        Dict with ``suggestion``, ``reasoning``, and ``confidence`` (0–1).

    Note:
        Requires ``GEMINI_API_KEY`` environment variable to be set.
        Stub implementation — integrate ``google-generativeai`` SDK to activate.
    """
    gemini_key = os.environ.get("GEMINI_API_KEY", "")
    if not gemini_key:
        log.warning(
            "ai_mediator_skipped",
            order_id=order_id,
            reason="GEMINI_API_KEY not set",
            step="ai_mediator_suggest",
        )
        return {
            "suggestion": None,
            "reasoning": "AI mediator not configured (GEMINI_API_KEY missing).",
            "confidence": 0.0,
        }

    # TODO: integrate google-generativeai SDK
    # import google.generativeai as genai
    # genai.configure(api_key=gemini_key)
    # model = genai.GenerativeModel("gemini-pro")
    # prompt = build_mediation_prompt(order_id, chat_history)
    # response = await model.generate_content_async(prompt)
    log.info(
        "ai_mediator_stub_called",
        order_id=order_id,
        chat_messages=len(chat_history) if chat_history else 0,
        step="ai_mediator_suggest",
    )
    return {
        "suggestion": "neutral",
        "reasoning": "AI mediation stub — real Gemini integration pending.",
        "confidence": 0.0,
    }
