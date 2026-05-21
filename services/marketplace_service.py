"""Marketplace services — handling Ads, Payment Details, and Reviews."""

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.marketplace import Ad, AdType, PriceType, Review, UserPaymentDetail


class MarketplaceService:
    """Service layer for marketplace operations."""

    @staticmethod
    async def create_ad(
        session: AsyncSession,
        maker_id: int,
        ad_type: AdType,
        asset: str,
        fiat: str,
        price_type: PriceType,
        price_value: float,
        min_limit: float,
        max_limit: float,
        payment_method_ids: str,
        chain: str | None = None,
        terms: str | None = None,
    ) -> Ad:
        """Create a new P2P advertisement."""
        ad = Ad(
            maker_id=maker_id,
            type=ad_type,
            asset=asset,
            fiat=fiat,
            price_type=price_type,
            price_value=price_value,
            min_limit=min_limit,
            max_limit=max_limit,
            payment_method_ids=payment_method_ids,
            chain=chain,
            terms=terms,
        )
        session.add(ad)
        await session.flush()
        return ad

    @staticmethod
    async def get_active_ads(
        session: AsyncSession, asset: str, fiat: str, ad_type: AdType
    ) -> Sequence[Ad]:
        """Fetch active ads for the orderbook."""
        stmt = (
            select(Ad)
            .where(Ad.is_active.is_(True), Ad.asset == asset, Ad.fiat == fiat, Ad.type == ad_type)
            .order_by(Ad.price_value.desc() if ad_type == AdType.buy else Ad.price_value.asc())
        )
        result = await session.execute(stmt)
        return result.scalars().all()

    @staticmethod
    async def add_user_payment_detail(
        session: AsyncSession,
        user_id: int,
        payment_method_id: int,
        account_name: str,
        account_number: str,
    ) -> UserPaymentDetail:
        """Save a user's fiat payment details."""
        detail = UserPaymentDetail(
            user_id=user_id,
            payment_method_id=payment_method_id,
            account_name=account_name,
            account_number=account_number,
        )
        session.add(detail)
        await session.flush()
        return detail

    @staticmethod
    async def get_user_payment_details(
        session: AsyncSession, user_id: int
    ) -> Sequence[UserPaymentDetail]:
        """Get all active payment details for a user."""
        stmt = select(UserPaymentDetail).where(
            UserPaymentDetail.user_id == user_id, UserPaymentDetail.is_active.is_(True)
        )
        result = await session.execute(stmt)
        return result.scalars().all()

    @staticmethod
    async def add_review(
        session: AsyncSession,
        order_id: uuid.UUID,
        reviewer_id: int,
        target_id: int,
        is_positive: bool,
        comment: str | None = None,
    ) -> Review:
        """Leave feedback after a trade."""
        review = Review(
            order_id=order_id,
            reviewer_id=reviewer_id,
            target_id=target_id,
            is_positive=is_positive,
            comment=comment,
        )
        session.add(review)
        await session.flush()
        return review

    @staticmethod
    async def get_user_reputation(session: AsyncSession, user_id: int) -> dict[str, int]:
        """Calculate basic user reputation from reviews."""
        stmt = select(Review.is_positive).where(Review.target_id == user_id)
        result = await session.execute(stmt)
        reviews = result.scalars().all()

        total = len(reviews)
        positive = sum(1 for r in reviews if r)
        return {
            "total_reviews": total,
            "positive_reviews": positive,
            "completion_rate": int((positive / total) * 100) if total > 0 else 100,
        }

    @staticmethod
    async def get_all_active_ads(session: AsyncSession, fiat: str | None = None) -> Sequence[Ad]:
        """Fetch all active ads, optionally filtered by fiat."""
        stmt = select(Ad).where(Ad.is_active.is_(True))
        if fiat:
            stmt = stmt.where(Ad.fiat == fiat)
        stmt = stmt.order_by(Ad.created_at.desc())
        result = await session.execute(stmt)
        return result.scalars().all()

    @staticmethod
    async def get_ad_details(session: AsyncSession, ad_id: int) -> dict[str, Any] | None:
        """Fetch ad details as a dictionary."""
        stmt = select(Ad).where(Ad.id == ad_id).with_for_update()
        result = await session.execute(stmt)
        ad = result.scalar_one_or_none()
        if not ad:
            return None
        return {
            "id": ad.id,
            "maker_id": ad.maker_id,
            "type": ad.type,
            "asset": ad.asset,
            "fiat": ad.fiat,
            "price_value": ad.price_value,
            "min_limit": ad.min_limit,
            "max_limit": ad.max_limit,
            "chain": ad.chain,
            "terms": ad.terms,
        }
