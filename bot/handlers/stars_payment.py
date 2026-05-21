"""Handlers for Telegram Stars payment events (TMA Marketplace)."""

import structlog
from aiogram import Bot, F, Router
from aiogram.types import Message, PreCheckoutQuery
from aiogram.types.message import ContentType
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.product import DealStatus, MarketplaceDeal

log = structlog.get_logger(__name__)
router = Router(name="stars_payment")


@router.pre_checkout_query()
async def process_pre_checkout_query(
    pre_checkout_query: PreCheckoutQuery, session: AsyncSession
) -> None:
    """Validate payment before Telegram charges the user's Stars."""
    payload = pre_checkout_query.invoice_payload

    if not payload.startswith("deal:"):
        await pre_checkout_query.answer(ok=False, error_message="Invalid payload format")
        return

    deal_id = payload.split(":")[1]

    # Verify deal exists and is pending
    result = await session.execute(select(MarketplaceDeal).where(MarketplaceDeal.id == deal_id))
    deal = result.scalar_one_or_none()

    if not deal:
        await pre_checkout_query.answer(ok=False, error_message="Deal not found")
        return

    if deal.status != DealStatus.created:
        await pre_checkout_query.answer(ok=False, error_message="Deal is no longer active")
        return

    # We have 10 seconds to respond. All good -> ok=True
    await pre_checkout_query.answer(ok=True)
    log.info(
        "stars_pre_checkout_approved", deal_id=deal_id, user_id=pre_checkout_query.from_user.id
    )


@router.message(F.content_type == ContentType.SUCCESSFUL_PAYMENT)
async def process_successful_payment(message: Message, session: AsyncSession, bot: Bot) -> None:
    """Handle successful Stars payment and deliver the product."""
    payment = message.successful_payment
    payload = payment.invoice_payload

    if not payload.startswith("deal:"):
        return

    deal_id = payload.split(":")[1]

    # Update deal status using pessimistic lock
    result = await session.execute(
        select(MarketplaceDeal).where(MarketplaceDeal.id == deal_id).with_for_update()
    )
    deal = result.scalar_one_or_none()

    if not deal or deal.status != DealStatus.created:
        log.error("invalid_deal_on_successful_payment", deal_id=deal_id)
        return

    deal.status = DealStatus.paid
    deal.telegram_payment_charge_id = payment.telegram_payment_charge_id
    deal.provider_payment_charge_id = payment.provider_payment_charge_id

    # Auto-delivery logic if it's a digital good
    await deal.awaitable_attrs.product
    if deal.product.is_digital and deal.product.digital_content:
        deal.status = DealStatus.delivered
        await message.answer(
            f"🎉 Payment successful! Here is your product:\n\n{deal.product.digital_content}"
        )
    else:
        await message.answer(
            "🎉 Payment successful! The seller has been notified to deliver your product."
        )
        # Notify seller
        await bot.send_message(
            deal.product.seller_id,
            f"💰 New sale! A buyer purchased '{deal.product.title}'. Please deliver the product.",
        )

    session.add(deal)
    await session.flush()
    log.info("stars_payment_successful", deal_id=deal_id, user_id=message.from_user.id)
