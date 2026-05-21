"""Marketplace E-commerce service — handling products and deals with on-chain escrow."""

from __future__ import annotations

import uuid
from decimal import Decimal

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from db.models.product import CurrencyType, DealStatus, MarketplaceDeal, Product
from db.models.wallet import WalletChain
from services.wallet_service import generate_order_wallet
from utils.encryption import encrypt

log = structlog.get_logger(__name__)


class MarketplaceEcommerceService:
    """Service layer for e-commerce marketplace operations."""

    @staticmethod
    async def create_product(
        session: AsyncSession,
        seller_id: int,
        title: str,
        price: Decimal,
        currency_type: CurrencyType,
        description: str | None = None,
        is_digital: bool = True,
        digital_content: str | None = None,
        image_urls: list[str] | None = None,
        fiat_currency: str | None = None,
        crypto_asset: str | None = None,
        crypto_chain: WalletChain | None = None,
        crypto_network: str | None = None,
    ) -> Product:
        """Create a new marketplace product."""
        product = Product(
            seller_id=seller_id,
            title=title,
            description=description,
            price=price,
            currency_type=currency_type,
            is_digital=is_digital,
            digital_content=encrypt(digital_content) if digital_content else None,
            image_urls=image_urls or [],
            fiat_currency=fiat_currency,
            crypto_asset=crypto_asset,
            crypto_chain=crypto_chain,
            crypto_network=crypto_network,
        )
        session.add(product)
        await session.flush()

        log.info(
            "product_created",
            product_id=str(product.id),
            seller_id=seller_id,
            price=str(price),
            currency=currency_type,
            step="MarketplaceEcommerceService.create_product",
        )
        return product

    @staticmethod
    async def create_deal(
        session: AsyncSession,
        product_id: uuid.UUID,
        buyer_id: int,
        promo_code_str: str | None = None,
    ) -> MarketplaceDeal:
        """Initialize a new deal for a product.

        For CRYPTO deals, generates a fresh on-chain escrow wallet.
        """
        # Fetch product
        stmt = select(Product).where(Product.id == product_id)
        result = await session.execute(stmt)
        product = result.scalar_one_or_none()
        if not product:
            raise ValueError("Product not found")

        # Deduplicate active deals
        stmt_deal = select(MarketplaceDeal).where(
            MarketplaceDeal.product_id == product_id,
            MarketplaceDeal.buyer_id == buyer_id,
            MarketplaceDeal.status.in_([DealStatus.created, DealStatus.paid, DealStatus.delivered]),
        )
        existing = await session.execute(stmt_deal)
        if existing.scalar_one_or_none():
            raise ValueError("An active deal already exists for this product")

        # Anti-fraud check: Cannot buy own product
        if product.seller_id == buyer_id:
            raise ValueError("You cannot buy your own product")

        final_amount = product.price
        promo_id = None
        
        if promo_code_str:
            from sqlalchemy.sql import func
            from db.models.product import PromoCode, DiscountType
            
            stmt_promo = select(PromoCode).where(
                func.lower(PromoCode.code) == promo_code_str.lower(),
                PromoCode.seller_id == product.seller_id
            ).with_for_update()
            
            promo = (await session.execute(stmt_promo)).scalar_one_or_none()
            if not promo:
                raise ValueError("Invalid promo code")
            if promo.expires_at and promo.expires_at < func.now():
                raise ValueError("Promo code has expired")
            if promo.max_uses and promo.current_uses >= promo.max_uses:
                raise ValueError("Promo code usage limit reached")
                
            # Apply discount
            if promo.discount_type == DiscountType.percentage:
                discount_amount = (final_amount * promo.discount_value) / 100
                final_amount = final_amount - discount_amount
            else:
                final_amount = final_amount - promo.discount_value
                
            if final_amount < 0:
                final_amount = Decimal("0.00")
                
            promo.current_uses += 1
            promo_id = promo.id

        deal = MarketplaceDeal(
            product_id=product_id,
            buyer_id=buyer_id,
            seller_id=product.seller_id,
            original_amount=product.price,
            amount=final_amount,
            promo_code_id=promo_id,
            currency_type=product.currency_type,
            status=DealStatus.created,
        )

        # Handle On-Chain Escrow for CRYPTO
        if product.currency_type == CurrencyType.CRYPTO and product.crypto_chain:
            deal.blockchain = product.crypto_chain
            deal.network = product.crypto_network or "mainnet"

            # Generate escrow wallet
            wallet_data = await generate_order_wallet(product.crypto_chain.value)
            deal.escrow_wallet_address = wallet_data["address"]
            deal.escrow_wallet_private_key_enc = encrypt(wallet_data["private_key"])

            log.info(
                "deal_escrow_initialized",
                deal_id=str(deal.id),
                chain=deal.blockchain,
                address=deal.escrow_wallet_address,
                step="MarketplaceEcommerceService.create_deal",
            )

        session.add(deal)
        await session.flush()

        log.info(
            "deal_created",
            deal_id=str(deal.id),
            buyer_id=buyer_id,
            product_id=str(product_id),
            step="MarketplaceEcommerceService.create_deal",
        )
        return deal

    @staticmethod
    async def get_deal(
        session: AsyncSession,
        deal_id: uuid.UUID,
        for_update: bool = False,
    ) -> MarketplaceDeal | None:
        """Fetch a deal with its product."""
        stmt = (
            select(MarketplaceDeal)
            .where(MarketplaceDeal.id == deal_id)
            .options(joinedload(MarketplaceDeal.product))
        )
        if for_update:
            stmt = stmt.with_for_update()

        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def deliver_deal(
        session: AsyncSession,
        deal: MarketplaceDeal,
    ) -> None:
        """Mark deal as delivered (seller action)."""
        if deal.status != DealStatus.paid:
            raise ValueError("Deal must be paid to be delivered")

        deal.status = DealStatus.delivered
        await session.flush()

        log.info(
            "deal_delivered",
            deal_id=str(deal.id),
            seller_id=deal.seller_id,
            step="MarketplaceEcommerceService.deliver_deal",
        )

    @staticmethod
    async def complete_deal(
        session: AsyncSession,
        deal: MarketplaceDeal,
    ) -> None:
        """Complete the deal and release funds (buyer action)."""
        if deal.status != DealStatus.delivered:
            raise ValueError("Deal must be delivered to be completed")

        deal.status = DealStatus.completed
        await session.flush()

        # Trigger on-chain release in background worker
        if deal.currency_type in (CurrencyType.CRYPTO, CurrencyType.XTR):
            from tasks.payout_worker import process_payout_to_seller
            import asyncio
            asyncio.create_task(process_payout_to_seller(deal.id))

        log.info(
            "deal_completed",
            deal_id=str(deal.id),
            buyer_id=deal.buyer_id,
            step="MarketplaceEcommerceService.complete_deal",
        )
