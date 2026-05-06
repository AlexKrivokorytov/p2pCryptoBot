"""Tests for Marketplace ORM models (Ads, Reviews, etc.)."""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.marketplace import (
    Ad,
    AdType,
    PriceType,
    ReferralReward,
    Review,
)
from db.models.order import Order, OrderStatus, OrderType, SupportedAsset
from db.models.user import User

pytestmark = pytest.mark.asyncio


async def test_create_and_query_ad(session: AsyncSession):
    """Test creating a P2P advertisement."""
    user = User(telegram_id=123, username="maker", first_name="Maker")
    session.add(user)
    await session.flush()

    ad = Ad(
        maker_id=user.telegram_id,
        type=AdType.sell,
        asset="USDT",
        fiat="RUB",
        price_type=PriceType.fixed,
        price_value=95.50,
        min_limit=1000.0,
        max_limit=50000.0,
        payment_method_ids="1,2",
    )
    session.add(ad)
    await session.flush()

    assert ad.id is not None

    # Query it back
    stmt = select(Ad).where(Ad.maker_id == user.telegram_id)
    result = await session.execute(stmt)
    fetched_ad = result.scalar_one()

    assert fetched_ad.fiat == "RUB"
    assert fetched_ad.type == AdType.sell


async def test_create_review(session: AsyncSession):
    """Test leaving a review on an order."""
    user = User(telegram_id=123, username="maker", first_name="Maker")
    session.add(user)
    await session.flush()

    # Create a dummy order
    order_id = uuid.uuid4()
    order = Order(
        id=order_id,
        maker_id=user.telegram_id,
        taker_id=user.telegram_id,  # just for test
        order_type=OrderType.buy_crypto,
        asset=SupportedAsset.USDT,
        fiat_currency="RUB",
        fiat_amount=1000,
        amount=10,
        status=OrderStatus.completed,
    )
    session.add(order)
    await session.flush()

    review = Review(
        order_id=order_id,
        reviewer_id=user.telegram_id,
        target_id=user.telegram_id,
        is_positive=True,
        comment="Fast and reliable!",
    )
    session.add(review)
    await session.flush()

    assert review.id is not None
    assert review.is_positive is True


async def test_referral_reward(session: AsyncSession):
    """Test referral reward logging."""
    user = User(telegram_id=123, username="maker", first_name="Maker")
    session.add(user)
    await session.flush()

    reward = ReferralReward(
        referrer_id=user.telegram_id,
        referred_user_id=user.telegram_id,
        asset="USDT",
        amount=1.5,
    )
    session.add(reward)
    await session.flush()

    assert reward.id is not None
    assert reward.amount == 1.5
