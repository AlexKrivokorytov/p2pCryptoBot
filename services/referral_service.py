"""Referral system service — handles reward calculations and tracking."""

import uuid
from decimal import Decimal

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.marketplace import ReferralReward
from db.models.user import User

log = structlog.get_logger(__name__)


class ReferralService:
    """Service layer for the referral program."""

    @staticmethod
    async def process_referral_reward(
        session: AsyncSession,
        order_id: uuid.UUID | None,
        deal_id: uuid.UUID | None,
        referred_user_id: int,
        asset: str,
        total_fee: float,
        reward_percentage: float = 0.20,  # 20% of the platform fee goes to the referrer
    ) -> ReferralReward | None:
        """Calculate and store a referral reward if the user was referred."""
        if not order_id and not deal_id:
            raise ValueError("Must provide either order_id or deal_id")

        # 1. Find who referred this user
        stmt = select(User.referred_by_id).where(User.telegram_id == referred_user_id)
        result = await session.execute(stmt)
        referrer_id = result.scalar_one_or_none()

        if not referrer_id or total_fee <= 0:
            return None

        # 2. Calculate reward
        reward_amount_float = total_fee * reward_percentage
        if reward_amount_float <= 0:
            return None

        reward_amount = Decimal(str(reward_amount_float))

        # 3. Lock referrer to credit balance (Financial operation)
        stmt_referrer = select(User).where(User.telegram_id == referrer_id).with_for_update()
        res_referrer = await session.execute(stmt_referrer)
        referrer = res_referrer.scalar_one_or_none()

        if not referrer:
            log.warning("referrer_not_found_for_reward", referrer_id=referrer_id)
            return None

        referrer.referral_balance += reward_amount

        # 4. Create reward record
        reward = ReferralReward(
            referrer_id=referrer_id,
            referred_user_id=referred_user_id,
            order_id=order_id,
            deal_id=deal_id,
            asset=asset,
            amount=reward_amount,
        )
        session.add(reward)
        await session.flush()

        log.info(
            "referral_reward_processed",
            referrer_id=referrer_id,
            referred_user_id=referred_user_id,
            amount=str(reward_amount),
            asset=asset,
            deal_id=str(deal_id) if deal_id else None,
            order_id=str(order_id) if order_id else None,
            step="process_referral_reward",
        )

        return reward
