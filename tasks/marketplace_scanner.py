"""Background task to scan on-chain deposits for Marketplace Deals."""

from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import joinedload

if TYPE_CHECKING:
    from aiogram import Bot

from db.models.product import DealStatus, MarketplaceDeal
from services.marketplace_notifications import notify_deal_paid
from services.wallet_service import _get_provider

log = structlog.get_logger(__name__)


class MarketplaceScanner:
    """Scanner that monitors escrow wallets for Marketplace deals."""

    def __init__(
        self,
        bot: Bot,
        session_maker: async_sessionmaker[AsyncSession],
        interval_sec: int = 60,
    ):
        self.bot = bot
        self.session_maker = session_maker
        self.interval_sec = interval_sec
        self._running = False

    async def run(self) -> None:
        """Start the scanner loop."""
        if self._running:
            return

        self._running = True
        log.info("marketplace_scanner_started", interval=self.interval_sec)

        while self._running:
            try:
                await self._scan_once()
            except Exception as e:
                log.error("marketplace_scanner_error", error=str(e), exc_info=True)

            await asyncio.sleep(self.interval_sec)

    def stop(self) -> None:
        """Stop the scanner loop."""
        self._running = False
        log.info("marketplace_scanner_stopped")

    async def _scan_once(self) -> None:
        """Check balances of all created deals awaiting crypto deposit."""
        async with self.session_maker() as session:
            # Fetch created deals with escrow wallets
            stmt = (
                select(MarketplaceDeal)
                .options(joinedload(MarketplaceDeal.product))
                .where(
                    MarketplaceDeal.status == DealStatus.created,
                    MarketplaceDeal.escrow_wallet_address.is_not(None),
                    MarketplaceDeal.blockchain.is_not(None),
                )
            )
            result = await session.execute(stmt)
            deals = result.scalars().all()

            if not deals:
                return

            for deal in deals:
                try:
                    await self._check_deal_deposit(session, deal)
                except Exception as e:
                    await session.rollback()
                    log.warning(
                        "marketplace_scanner_deal_check_failed",
                        deal_id=str(deal.id),
                        error=str(e),
                    )

    async def _check_deal_deposit(self, session: AsyncSession, deal: MarketplaceDeal) -> None:
        """Check balance for a single deal and mark as paid if funded."""
        if not deal.blockchain:
            return

        # Lock the deal
        result = await session.execute(
            select(MarketplaceDeal).where(MarketplaceDeal.id == deal.id).with_for_update()
        )
        locked_deal = result.scalar_one_or_none()
        if not locked_deal or locked_deal.status != DealStatus.created:
            await session.rollback()
            return

        provider = _get_provider(locked_deal.blockchain.value)
        # Default to USDT for crypto deals if not specified
        asset = locked_deal.product.crypto_asset or "USDT"

        # Fetch current balance
        # For Marketplace, we assume simple transfer for now.
        # Seller covers gas for release, so buyer only sends the exact price.
        balance = await provider.get_balance(locked_deal.escrow_wallet_address, asset)
        required = Decimal(str(locked_deal.amount))

        if balance >= required:
            log.info(
                "marketplace_deal_deposit_detected",
                deal_id=str(locked_deal.id),
                address=locked_deal.escrow_wallet_address,
                balance=str(balance),
                required=str(required),
            )

            locked_deal.status = DealStatus.paid
            await session.commit()

            log.info(
                "marketplace_deal_marked_paid",
                deal_id=str(locked_deal.id),
                status=locked_deal.status,
                step="MarketplaceScanner._check_deal_deposit",
            )

            # Notify seller
            asyncio.create_task(
                notify_deal_paid(
                    self.bot,
                    seller_id=locked_deal.seller_id,
                    deal_id=str(locked_deal.id),
                    product_title=deal.product.title,
                    amount=float(locked_deal.amount),
                    currency=asset,
                )
            )
        else:
            await session.rollback()
