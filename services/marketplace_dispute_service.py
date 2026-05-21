"""Marketplace dispute service — open and resolve disputes for Mini App deals.

This module handles only *marketplace* deals (MarketplaceDeal).
Classic P2P order disputes remain in services/dispute_service.py.

Business rules:
- Dispute may be opened only by buyer or seller when status is ``paid`` or ``delivered``.
- A cooldown of DISPUTE_COOLDOWN_MINUTES is enforced after deal creation.
- Escrow funds are NOT touched until admin resolves the dispute.
- Resolution "seller" → transfer_from_deal_wallet to seller's address.
- Resolution "buyer" + CRYPTO → transfer_from_deal_wallet back to buyer_wallet_address.
- Resolution "buyer" + XTR → Telegram refundStarPayment API call.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import structlog
from aiogram import Bot
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.product import CurrencyType, DealStatus, MarketplaceDeal
from db.models.user import User
from services.marketplace_notifications import (
    get_bot,
    notify_dispute_opened,
    notify_dispute_resolved,
    notify_marketplace_admin_dispute,
)

log = structlog.get_logger(__name__)

# Minimum minutes after deal creation before a dispute may be raised.
DISPUTE_COOLDOWN_MINUTES: int = 15

# Valid resolution values accepted by resolve_marketplace_dispute.
VALID_RESOLUTIONS: frozenset[str] = frozenset({"buyer", "seller"})


async def open_marketplace_dispute(
    session: AsyncSession,
    *,
    deal_id: str,
    initiator_id: int,
    reason: str,
) -> dict[str, Any]:
    """Raise a dispute on a marketplace deal.

    Transitions deal status ``paid`` | ``delivered`` → ``dispute``.
    Notifies the opposing party and the admin chat.

    Args:
        session: Active async SQLAlchemy session.
        deal_id: UUID string of the deal.
        initiator_id: Telegram user ID of the party raising the dispute.
        reason: Human-readable description of the problem (already sanitized by caller).

    Returns:
        Dict with ``deal_id``, ``status``, and ``initiator`` role.

    Raises:
        ValueError: If the deal cannot be disputed in its current state,
                    the cooldown has not elapsed, or the caller is not a participant.
    """
    async with session.begin():
        result = await session.execute(
            select(MarketplaceDeal)
            .where(MarketplaceDeal.id == uuid.UUID(deal_id))
            .with_for_update()
        )
        deal = result.scalar_one_or_none()
        if deal is None:
            raise ValueError(f"Deal {deal_id!r} not found")

        # Authorization: only buyer or seller may open a dispute
        if initiator_id not in {deal.buyer_id, deal.seller_id}:
            raise ValueError("Only the buyer or seller may open a dispute on this deal")

        # Status guard
        if deal.status not in {DealStatus.paid, DealStatus.delivered}:
            raise ValueError(
                f"Cannot open a dispute on a deal with status {deal.status!r}. "
                "Dispute is only allowed after payment."
            )

        # Cooldown guard
        now = datetime.now(tz=UTC)
        deal_age = now - deal.created_at.replace(tzinfo=UTC)
        if deal_age < timedelta(minutes=DISPUTE_COOLDOWN_MINUTES):
            remaining = DISPUTE_COOLDOWN_MINUTES - int(deal_age.total_seconds() / 60)
            raise ValueError(
                f"Dispute can be opened {DISPUTE_COOLDOWN_MINUTES} minutes after deal creation. "
                f"Please wait {remaining} more minute(s)."
            )

        # Persist dispute
        deal.status = DealStatus.dispute
        deal.dispute_reason = reason
        deal.dispute_opened_at = now

        initiator_role = "buyer" if initiator_id == deal.buyer_id else "seller"
        deal_id_str = str(deal.id)
        amount = float(deal.amount)
        currency = deal.currency_type.value

    log.info(
        "marketplace_dispute_opened",
        deal_id=deal_id_str,
        initiator_id=initiator_id,
        initiator_role=initiator_role,
        step="open_marketplace_dispute",
    )

    # Fire-and-forget notifications (outside the transaction)
    bot = get_bot()
    await notify_dispute_opened(bot, deal.buyer_id, deal.seller_id, deal_id_str, reason)
    await notify_marketplace_admin_dispute(
        bot,
        deal_id=deal_id_str,
        initiator_id=initiator_id,
        initiator_role=initiator_role,
        amount=amount,
        currency=currency,
        reason=reason,
    )

    return {"deal_id": deal_id_str, "status": DealStatus.dispute, "initiator": initiator_role}


async def resolve_marketplace_dispute(
    session: AsyncSession,
    bot: Bot,
    *,
    deal_id: str,
    admin_id: int,
    resolution: Literal["buyer", "seller"],
    comment: str = "",
) -> dict[str, Any]:
    """Resolve a marketplace dispute by admin decision.

    Resolution actions:
    - ``seller`` → release escrow to seller wallet.
    - ``buyer``  → refund escrow to buyer (on-chain) or refund Stars (XTR).

    Args:
        session: Active async SQLAlchemy session.
        bot: Bot instance for sending notifications and XTR refunds.
        deal_id: UUID string of the deal.
        admin_id: Telegram ID of the resolving admin.
        resolution: ``"buyer"`` or ``"seller"``.
        comment: Optional admin comment stored on the deal.

    Returns:
        Dict with ``deal_id``, final ``status``, and ``resolution``.

    Raises:
        ValueError: If resolution is invalid, deal is not in dispute, or
                    required wallet data is missing for on-chain resolution.
        RuntimeError: If the on-chain transfer or Stars refund fails.
    """
    if resolution not in VALID_RESOLUTIONS:
        raise ValueError(f"Invalid resolution {resolution!r}. Must be one of {VALID_RESOLUTIONS}")

    async with session.begin():
        result = await session.execute(
            select(MarketplaceDeal)
            .where(MarketplaceDeal.id == uuid.UUID(deal_id))
            .with_for_update()
        )
        deal = result.scalar_one_or_none()
        if deal is None:
            raise ValueError(f"Deal {deal_id!r} not found")
        if deal.status != DealStatus.dispute:
            raise ValueError(
                f"Deal {deal_id!r} is not in dispute status (current: {deal.status!r})"
            )

        final_status: DealStatus
        tx_hash: str | None = None

        if resolution == "seller":
            # Release escrow → seller's wallet
            final_status = DealStatus.completed
            buyer = await session.get(User, deal.buyer_id)
            if buyer:
                buyer.dispute_count_buyer += 1
                if buyer.dispute_count_buyer >= 3:
                    buyer.is_shadowbanned = True

            if deal.currency_type in (CurrencyType.CRYPTO, CurrencyType.XTR):
                from tasks.payout_worker import process_payout_to_seller
                import asyncio
                asyncio.create_task(process_payout_to_seller(deal.id))
        else:
            # Refund → buyer
            final_status = DealStatus.cancelled
            seller = await session.get(User, deal.seller_id)
            if seller:
                seller.dispute_count_seller += 1
                if seller.dispute_count_seller >= 3:
                    seller.is_shadowbanned = True

            if deal.currency_type == CurrencyType.CRYPTO:
                tx_hash = await _refund_to_buyer_crypto(session, deal)
            elif deal.currency_type == CurrencyType.XTR:
                await _refund_to_buyer_xtr(bot, deal)

        # Persist resolution metadata
        deal.status = final_status
        deal.dispute_resolution = resolution
        deal.dispute_resolved_by = admin_id
        deal.dispute_resolution_comment = comment or None
        if tx_hash:
            deal.tx_hash_release = tx_hash

    deal_id_str = str(deal.id)
    log.info(
        "marketplace_dispute_resolved",
        deal_id=deal_id_str,
        admin_id=admin_id,
        resolution=resolution,
        final_status=final_status,
        step="resolve_marketplace_dispute",
    )

    # Notify both parties
    await notify_dispute_resolved(
        bot,
        buyer_id=deal.buyer_id,
        seller_id=deal.seller_id,
        deal_id=deal_id_str,
        resolution=resolution,
        comment=comment,
    )

    return {"deal_id": deal_id_str, "status": final_status, "resolution": resolution}


# ── Internal resolution helpers ───────────────────────────────────────────────





async def _refund_to_buyer_crypto(session: AsyncSession, deal: MarketplaceDeal) -> str:
    """Refund escrow funds to buyer's on-chain wallet.

    Args:
        session: Active async SQLAlchemy session.
        deal: The locked MarketplaceDeal row.

    Returns:
        Transaction hash string.

    Raises:
        ValueError: If buyer_wallet_address is not set on the deal.
        RuntimeError: If on-chain transfer fails.
    """
    from services.wallet_service import transfer_from_deal_wallet

    if not deal.buyer_wallet_address:
        raise ValueError(f"Deal {deal.id} has no buyer_wallet_address — cannot refund on-chain")

    asset = deal.product.crypto_asset or "USDT"
    try:
        return await transfer_from_deal_wallet(
            session=session,
            deal_id=str(deal.id),
            chain=deal.blockchain.value,  # type: ignore[union-attr]
            to_address=deal.buyer_wallet_address,
            asset=asset,
            amount=deal.amount,
        )
    except Exception as exc:
        log.error(
            "dispute_refund_to_buyer_failed",
            deal_id=str(deal.id),
            error=str(exc),
        )
        raise RuntimeError(f"On-chain refund to buyer failed: {exc}") from exc


async def _refund_to_buyer_xtr(bot: Bot, deal: MarketplaceDeal) -> None:
    """Refund Telegram Stars to buyer via the Telegram Bot API.

    Args:
        bot: Aiogram Bot instance.
        deal: The locked MarketplaceDeal row.

    Raises:
        ValueError: If the deal is missing the required payment charge ID.
        RuntimeError: If the Telegram refund API call fails.
    """
    if not deal.telegram_payment_charge_id:
        raise ValueError(f"Deal {deal.id} has no telegram_payment_charge_id — cannot refund Stars")

    try:
        await bot.refund_star_payment(
            user_id=deal.buyer_id,
            telegram_payment_charge_id=deal.telegram_payment_charge_id,
        )
        log.info(
            "dispute_xtr_refund_ok",
            deal_id=str(deal.id),
            buyer_id=deal.buyer_id,
            step="_refund_to_buyer_xtr",
        )
    except Exception as exc:
        log.error(
            "dispute_xtr_refund_failed",
            deal_id=str(deal.id),
            buyer_id=deal.buyer_id,
            error=str(exc),
        )
        raise RuntimeError(f"Stars refund failed: {exc}") from exc
