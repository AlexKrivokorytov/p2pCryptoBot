"""Referral system service — handles reward calculations and tracking."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.marketplace import ReferralReward
from db.models.user import User


class ReferralService:
    """Service layer for the referral program."""

    @staticmethod
    async def process_referral_reward(
        session: AsyncSession,
        order_id: uuid.UUID,
        referred_user_id: int,
        asset: str,
        total_fee: float,
        reward_percentage: float = 0.20,  # 20% of the platform fee goes to the referrer
    ) -> ReferralReward | None:
        """Calculate and store a referral reward if the user was referred."""
        # 1. Find who referred this user
        stmt = select(User.referred_by_id).where(User.telegram_id == referred_user_id)
        result = await session.execute(stmt)
        referrer_id = result.scalar_one_or_none()

        if not referrer_id or total_fee <= 0:
            return None

        # 2. Calculate reward
        reward_amount = total_fee * reward_percentage
        if reward_amount <= 0:
            return None

        # 3. Create reward record
        reward = ReferralReward(
            referrer_id=referrer_id,
            referred_user_id=referred_user_id,
            order_id=order_id,
            asset=asset,
            amount=reward_amount,
        )
        session.add(reward)
        await session.flush()

        # Note: Actual balance credit depends on whether we hold platform funds
        # in the bot wallet or a separate master wallet.

        return reward
