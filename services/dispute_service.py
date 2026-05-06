"""Dispute service — raise, resolve, and AI-mediate P2P order disputes."""

from __future__ import annotations

import asyncio
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

    Note:
        We intentionally do NOT perform a separate pre-check read here.
        Both ``release_escrow`` and ``refund_escrow`` open their own
        ``SELECT ... FOR UPDATE`` transaction and validate the order status
        atomically. A separate pre-check without a lock would create a race
        window where two concurrent moderator actions could both pass the
        ``status == dispute`` check and then both execute a transfer
        (double-spend). Removing it here forces all validation to happen
        inside the atomic locked transaction.
    """
    if decision not in VALID_DECISIONS:
        raise ValueError(f"Invalid decision {decision!r}. Must be one of {VALID_DECISIONS}")

    # Execute the appropriate escrow action.
    # release_escrow / refund_escrow each perform SELECT ... FOR UPDATE
    # and validate order.status atomically — no separate pre-check needed.
    if decision == "taker_wins":
        result_data = await escrow_service.release_escrow(
            session, crypto_pay, order_id=order_id, force=True, require_dispute=True
        )
    else:
        # maker_wins or cancel both refund to maker
        result_data = await escrow_service.refund_escrow(
            session, crypto_pay, order_id=order_id, force=True, require_dispute=True
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
    """Ask the Gemini AI mediator to suggest dispute resolution.

    Reads the trade chat history and returns a suggested decision with reasoning.
    The suggestion is advisory only — a human moderator makes the final decision.

    Args:
        order_id: UUID string of the disputed order.
        chat_history: List of {"role": "maker"|"taker", "text": "..."} messages.

    Returns:
        Dict with keys:
        - suggestion: "taker_wins" | "maker_wins" | "neutral" | None
        - reasoning: Human-readable explanation string
        - confidence: Float 0.0–1.0
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

    import google.generativeai as genai  # noqa: F401

    getattr(genai, "configure")(api_key=gemini_key)  # noqa: B009
    model_class = getattr(genai, "GenerativeModel")  # noqa: B009
    model = model_class("gemini-2.0-flash")

    history_text = ""
    if chat_history:
        lines = [f"[{m['role'].upper()}]: {m['text']}" for m in chat_history]
        history_text = "\n".join(lines)

    prompt = (
        f"You are a neutral P2P trade dispute mediator. "
        f"Analyze this trade dispute and suggest a resolution.\n\n"
        f"Order ID: {order_id}\n\n"
        f"Trade Chat History:\n{history_text or 'No messages exchanged.'}\n\n"
        "Based on the chat history, respond ONLY with valid JSON in this exact format:\n"
        '{"suggestion": "taker_wins" or "maker_wins" or "neutral", '
        '"reasoning": "one paragraph explanation", '
        '"confidence": 0.0 to 1.0}\n\n'
        "Rules:\n"
        "- taker_wins: buyer should receive the crypto\n"
        "- maker_wins: seller should be refunded\n"
        "- neutral: insufficient evidence, human review required\n"
        "- confidence below 0.6 means you are not sure — prefer neutral\n"
        "Respond with JSON only. No preamble, no markdown."
    )

    try:
        response = await asyncio.to_thread(model.generate_content, prompt)
        raw = response.text.strip()

        # Strip markdown fences if model adds them
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        import json

        parsed = json.loads(raw.strip())

        suggestion = parsed.get("suggestion", "neutral")
        if suggestion not in {"taker_wins", "maker_wins", "neutral"}:
            suggestion = "neutral"

        result = {
            "suggestion": suggestion,
            "reasoning": str(parsed.get("reasoning", "No reasoning provided.")),
            "confidence": float(parsed.get("confidence", 0.0)),
        }
        log.info(
            "ai_mediator_responded",
            order_id=order_id,
            suggestion=suggestion,
            confidence=result["confidence"],
            step="ai_mediator_suggest",
        )
        return result

    except Exception as exc:
        log.error(
            "ai_mediator_failed",
            order_id=order_id,
            error=str(exc),
            step="ai_mediator_suggest",
        )
        return {
            "suggestion": "neutral",
            "reasoning": f"AI mediator encountered an error: {exc}",
            "confidence": 0.0,
        }
