"""Tests for stars_payment.py handlers."""

from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram import Bot
from aiogram.types import Message, PreCheckoutQuery, SuccessfulPayment
from aiogram.types import User as TgUser
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.handlers import stars_payment as stars_handlers
from db.models.product import CurrencyType, DealStatus, MarketplaceDeal, Product
from db.models.user import User


async def _make_user(session: AsyncSession, telegram_id: int, username: str) -> User:
    """Helper to create and flush a User row to avoid foreign key violations."""
    user = User(telegram_id=telegram_id, username=username, first_name="Test")
    session.add(user)
    await session.flush()
    return user


@pytest.mark.integration
@pytest.mark.asyncio
async def test_pre_checkout_invalid_payload(session: AsyncSession) -> None:
    """PreCheckoutQuery with invalid payload is rejected."""
    query = AsyncMock(spec=PreCheckoutQuery)
    query.invoice_payload = "invalid_payload"
    query.answer = AsyncMock()

    await stars_handlers.process_pre_checkout_query(query, session)
    query.answer.assert_called_once_with(ok=False, error_message="Invalid payload format")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_pre_checkout_deal_not_found(session: AsyncSession) -> None:
    """PreCheckoutQuery is rejected if deal does not exist."""
    query = AsyncMock(spec=PreCheckoutQuery)
    query.invoice_payload = f"deal:{uuid.uuid4()}"
    query.answer = AsyncMock()

    await stars_handlers.process_pre_checkout_query(query, session)
    query.answer.assert_called_once_with(ok=False, error_message="Deal not found")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_pre_checkout_deal_not_active(session: AsyncSession) -> None:
    """PreCheckoutQuery is rejected if deal is not in 'created' status."""
    # Create users first
    async with session.begin():
        await _make_user(session, telegram_id=5001, username="seller5001")
        await _make_user(session, telegram_id=5002, username="buyer5002")

    # Create product and deal in DB
    async with session.begin():
        product = Product(
            seller_id=5001,
            title="Stars Product 1",
            price=Decimal("10.0"),
            currency_type=CurrencyType.XTR,
        )
        session.add(product)

    async with session.begin():
        deal = MarketplaceDeal(
            product_id=product.id,
            buyer_id=5002,
            seller_id=5001,
            amount=Decimal("10.0"),
            status=DealStatus.paid,  # Not created
            currency_type=CurrencyType.XTR,
        )
        session.add(deal)

    query = AsyncMock(spec=PreCheckoutQuery)
    query.invoice_payload = f"deal:{deal.id}"
    query.answer = AsyncMock()

    await stars_handlers.process_pre_checkout_query(query, session)
    query.answer.assert_called_once_with(ok=False, error_message="Deal is no longer active")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_pre_checkout_happy_path(session: AsyncSession) -> None:
    """PreCheckoutQuery is accepted for active deal."""
    async with session.begin():
        await _make_user(session, telegram_id=5003, username="seller5003")
        await _make_user(session, telegram_id=5004, username="buyer5004")

    async with session.begin():
        product = Product(
            seller_id=5003,
            title="Stars Product 2",
            price=Decimal("10.0"),
            currency_type=CurrencyType.XTR,
        )
        session.add(product)

    async with session.begin():
        deal = MarketplaceDeal(
            product_id=product.id,
            buyer_id=5004,
            seller_id=5003,
            amount=Decimal("10.0"),
            status=DealStatus.created,
            currency_type=CurrencyType.XTR,
        )
        session.add(deal)

    query = AsyncMock(spec=PreCheckoutQuery)
    query.invoice_payload = f"deal:{deal.id}"
    query.from_user = MagicMock(spec=TgUser)
    query.from_user.id = 5004
    query.answer = AsyncMock()

    await stars_handlers.process_pre_checkout_query(query, session)
    query.answer.assert_called_once_with(ok=True)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_successful_payment_missing_data(session: AsyncSession) -> None:
    """successful_payment returns early if payment data is missing."""
    message = AsyncMock(spec=Message)
    message.successful_payment = None
    bot = AsyncMock(spec=Bot)

    await stars_handlers.process_successful_payment(message, session, bot)
    message.answer.assert_not_called()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_successful_payment_invalid_payload(session: AsyncSession) -> None:
    """successful_payment ignores non-deal payloads."""
    message = AsyncMock(spec=Message)
    message.successful_payment = MagicMock(spec=SuccessfulPayment)
    message.successful_payment.invoice_payload = "invalid_payload"
    bot = AsyncMock(spec=Bot)

    await stars_handlers.process_successful_payment(message, session, bot)
    message.answer.assert_not_called()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_successful_payment_digital_autodelivery(session: AsyncSession) -> None:
    """successful_payment auto-delivers digital goods."""
    async with session.begin():
        await _make_user(session, telegram_id=5005, username="seller5005")
        await _make_user(session, telegram_id=5006, username="buyer5006")

    async with session.begin():
        product = Product(
            seller_id=5005,
            title="Digital Product",
            price=Decimal("5.0"),
            currency_type=CurrencyType.XTR,
            is_digital=True,
            digital_content="SUPER_SECRET_KEY",
        )
        session.add(product)

    async with session.begin():
        deal = MarketplaceDeal(
            product_id=product.id,
            buyer_id=5006,
            seller_id=5005,
            amount=Decimal("5.0"),
            status=DealStatus.created,
            currency_type=CurrencyType.XTR,
        )
        session.add(deal)

    message = AsyncMock(spec=Message)
    message.from_user = MagicMock(spec=TgUser)
    message.from_user.id = 5006
    message.successful_payment = MagicMock(spec=SuccessfulPayment)
    message.successful_payment.invoice_payload = f"deal:{deal.id}"
    message.successful_payment.telegram_payment_charge_id = "tg_chg_1"
    message.successful_payment.provider_payment_charge_id = "prv_chg_1"
    message.answer = AsyncMock()

    bot = AsyncMock(spec=Bot)

    await stars_handlers.process_successful_payment(message, session, bot)

    message.answer.assert_called_once()
    assert "SUPER_SECRET_KEY" in message.answer.call_args[0][0]

    # Verify deal status is delivered in DB
    await session.commit()
    result = await session.execute(select(MarketplaceDeal).where(MarketplaceDeal.id == deal.id))
    db_deal = result.scalar_one()
    assert db_deal.status == DealStatus.delivered
    assert db_deal.telegram_payment_charge_id == "tg_chg_1"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_successful_payment_non_digital(session: AsyncSession) -> None:
    """successful_payment notifies seller for physical/manual goods."""
    async with session.begin():
        await _make_user(session, telegram_id=5007, username="seller5007")
        await _make_user(session, telegram_id=5008, username="buyer5008")

    async with session.begin():
        product = Product(
            seller_id=5007,
            title="Physical Product",
            price=Decimal("20.0"),
            currency_type=CurrencyType.XTR,
            is_digital=False,
        )
        session.add(product)

    async with session.begin():
        deal = MarketplaceDeal(
            product_id=product.id,
            buyer_id=5008,
            seller_id=5007,
            amount=Decimal("20.0"),
            status=DealStatus.created,
            currency_type=CurrencyType.XTR,
        )
        session.add(deal)

    message = AsyncMock(spec=Message)
    message.from_user = MagicMock(spec=TgUser)
    message.from_user.id = 5008
    message.successful_payment = MagicMock(spec=SuccessfulPayment)
    message.successful_payment.invoice_payload = f"deal:{deal.id}"
    message.successful_payment.telegram_payment_charge_id = "tg_chg_2"
    message.successful_payment.provider_payment_charge_id = "prv_chg_2"
    message.answer = AsyncMock()

    bot = AsyncMock(spec=Bot)
    bot.send_message = AsyncMock()

    await stars_handlers.process_successful_payment(message, session, bot)

    message.answer.assert_called_once()
    assert "seller has been notified" in message.answer.call_args[0][0]
    bot.send_message.assert_called_once_with(
        5007, "💰 New sale! A buyer purchased 'Physical Product'. Please deliver the product."
    )

    # Verify deal status is paid in DB
    await session.commit()
    result = await session.execute(select(MarketplaceDeal).where(MarketplaceDeal.id == deal.id))
    db_deal = result.scalar_one()
    assert db_deal.status == DealStatus.paid
