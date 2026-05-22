"""Tests for services/referral_service.py — coverage boost."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.user import User
from services.referral_service import ReferralService

pytestmark = [pytest.mark.integration, pytest.mark.unit]


@pytest.mark.asyncio
async def test_process_referral_reward_no_referrer(session: AsyncSession) -> None:
    """Should return None if user has no referrer."""
    user = User(telegram_id=123, username="test", referred_by_id=None)
    session.add(user)
    await session.commit()

    reward = await ReferralService.process_referral_reward(
        order_id=uuid.uuid4(),
        deal_id=None,
        referred_user_id=123,
        asset="USDT",
        total_fee=10.0,
    )
    assert reward is None


@pytest.mark.asyncio
async def test_process_referral_reward_zero_fee(session: AsyncSession) -> None:
    """Should return None if fee is zero or negative."""
    reward = await ReferralService.process_referral_reward(
        order_id=uuid.uuid4(),
        deal_id=None,
        referred_user_id=123,
        asset="USDT",
        total_fee=0.0,
    )
    assert reward is None


@pytest.mark.asyncio
async def test_process_referral_reward_success(session: AsyncSession) -> None:
    """Should create ReferralReward if user has referrer and fee > 0."""
    referrer = User(telegram_id=456, username="referrer")
    referred = User(telegram_id=123, username="referred", referred_by_id=456)
    session.add_all([referrer, referred])
    await session.commit()

    order_id = uuid.uuid4()
    # Create the order first to satisfy the FK constraint
    from db.models.order import Order, OrderStatus, OrderType, SupportedAsset

    order = Order(
        id=order_id,
        maker_id=456,
        asset=SupportedAsset.USDT,
        fiat_currency="USD",
        fiat_amount=100.0,
        amount=100.0,
        order_type=OrderType.sell_crypto,
        status=OrderStatus.completed,
    )
    session.add(order)
    await session.commit()

    reward = await ReferralService.process_referral_reward(
        order_id=order_id,
        deal_id=None,
        referred_user_id=123,
        asset="USDT",
        total_fee=100.0,
        reward_percentage=0.2,
    )

    assert reward is not None
    assert reward.referrer_id == 456
    assert reward.amount == 20.0
    assert reward.asset == "USDT"
    assert reward.order_id == order_id


@pytest.mark.asyncio
async def test_process_referral_reward_low_amount(session: AsyncSession) -> None:
    """Should return None if calculated reward is <= 0."""
    reward = await ReferralService.process_referral_reward(
        order_id=uuid.uuid4(),
        deal_id=None,
        referred_user_id=123,
        asset="USDT",
        total_fee=0.00000001,
        reward_percentage=0.0,
    )
    assert reward is None
