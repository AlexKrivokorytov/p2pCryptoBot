import asyncio
import logging
import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from db.engine import async_session_factory
from db.models.product import MarketplaceDeal, CurrencyType
from db.models.wallet import UserWallet
# Assuming services.wallet_service is available

log = logging.getLogger(__name__)

async def process_payout_to_seller(deal_id: uuid.UUID) -> None:
    """Release escrow funds to seller wallet. Fire-and-forget task."""
    try:
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
                return
            
            if deal.payout_status in ("sent", "manual"):
                return
            
            if deal.currency_type == CurrencyType.XTR:
                deal.payout_status = "manual"
                await session.commit()
                return
                
            if deal.currency_type == CurrencyType.CRYPTO and deal.blockchain:
                # Fetch seller's wallet
                stmt_wallet = select(UserWallet).where(
                    UserWallet.user_id == deal.seller_id, UserWallet.chain == deal.blockchain
                )
                wallet_res = await session.execute(stmt_wallet)
                seller_wallet = wallet_res.scalar_one_or_none()
                
                if not seller_wallet:
                    deal.payout_status = "failed"
                    deal.payout_error = f"Seller does not have a {deal.blockchain.value} wallet"
                    await session.commit()
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
                    deal.tx_hash_release = tx_hash
                    deal.payout_status = "sent"
                    await session.commit()
                    
                    log.info(
                        "payout_sent",
                        deal_id=str(deal.id),
                        tx_hash=tx_hash,
                        step="process_payout_to_seller"
                    )
                    
                    # Try to notify the seller
                    from services.marketplace_notifications import notify_seller_payout_sent
                    from bot.dynamic_loader import get_master_bot
                    bot = get_master_bot()
                    if bot:
                        await notify_seller_payout_sent(bot, deal)
                    
                except Exception as e:
                    log.error("payout_failed", deal_id=str(deal.id), error=str(e))
                    deal.payout_status = "failed"
                    deal.payout_error = str(e)
                    await session.commit()

    except Exception as e:
        log.error("process_payout_to_seller_fatal_error", error=str(e), deal_id=str(deal_id))
