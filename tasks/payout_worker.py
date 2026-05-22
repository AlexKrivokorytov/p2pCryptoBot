"""Background payout worker — releases escrow funds to seller after deal completion."""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from db.engine import async_session_factory
from db.models.product import CurrencyType, MarketplaceDeal
from db.models.wallet import UserWallet

log = structlog.get_logger(__name__)


async def process_payout_to_seller(deal_id: uuid.UUID) -> None:
    """Release escrow funds to seller wallet.

    Fire-and-forget task — called from dispute resolution and deal completion.
    Uses a separate session and session.begin() for each mutation to ensure
    proper transaction isolation.

    Args:
        deal_id: UUID of the MarketplaceDeal to process.
    """
    try:
        # Load deal with product eagerly to avoid awaitable_attrs
        # (MarketplaceDeal does not inherit AsyncAttrs mixin)
        async with async_session_factory() as session:
            stmt = (
                select(MarketplaceDeal)
                .options(joinedload(MarketplaceDeal.product))
                .where(MarketplaceDeal.id == deal_id)
                .with_for_update()
            )
            result = await session.execute(stmt)
            deal = result.scalar_one_or_none()

            if not deal:
                log.warning("payout_deal_not_found", deal_id=str(deal_id))
                return

            if deal.payout_status in ("sent", "manual"):
                log.info(
                    "payout_already_processed",
                    deal_id=str(deal_id),
                    status=deal.payout_status,
                )
                return

            if deal.currency_type == CurrencyType.XTR:
                async with session.begin():
                    deal.payout_status = "manual"
                log.info("payout_xtr_manual", deal_id=str(deal.id))
                return

            if deal.currency_type == CurrencyType.CRYPTO and deal.blockchain:
                # Fetch seller's wallet
                stmt_wallet = select(UserWallet).where(
                    UserWallet.user_id == deal.seller_id, UserWallet.chain == deal.blockchain
                )
                wallet_res = await session.execute(stmt_wallet)
                seller_wallet = wallet_res.scalar_one_or_none()

                if not seller_wallet:
                    async with session.begin():
                        deal.payout_status = "failed"
                        deal.payout_error = f"Seller does not have a {deal.blockchain.value} wallet"
                    log.error(
                        "payout_no_seller_wallet",
                        deal_id=str(deal.id),
                        blockchain=deal.blockchain.value,
                    )
                    return

                deal.seller_wallet_address = seller_wallet.address
                asset = deal.product.crypto_asset or "USDT"

                from services.wallet_service import transfer_from_deal_wallet

                try:
                    tx_hash = await transfer_from_deal_wallet(
                        session=session,
                        deal_id=str(deal.id),
                        chain=deal.blockchain.value,
                        to_address=seller_wallet.address,
                        asset=asset,
                        amount=deal.amount,
                    )
                    async with session.begin():
                        deal.tx_hash_release = tx_hash
                        deal.payout_status = "sent"

                    log.info(
                        "payout_sent",
                        deal_id=str(deal.id),
                        tx_hash=tx_hash,
                        step="process_payout_to_seller",
                    )

                    # Notify seller via the shared Bot singleton
                    from services.marketplace_notifications import (
                        get_bot,
                        notify_seller_payout_sent,
                    )

                    bot = get_bot()
                    await notify_seller_payout_sent(bot, deal)

                except Exception as exc:
                    log.error("payout_failed", deal_id=str(deal.id), error=str(exc))
                    async with session.begin():
                        deal.payout_status = "failed"
                        deal.payout_error = str(exc)

    except Exception as exc:
        log.error("process_payout_to_seller_fatal_error", error=str(exc), deal_id=str(deal_id))
