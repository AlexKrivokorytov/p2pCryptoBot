"""Integration tests for services/marketplace_dispute_service.py."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from aiogram import Bot
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.product import CurrencyType, DealStatus, MarketplaceDeal, Product
from db.models.user import User
from services.marketplace_dispute_service import (
    DISPUTE_COOLDOWN_MINUTES,
    open_marketplace_dispute,
    resolve_marketplace_dispute,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def mock_bot() -> AsyncMock:
    return AsyncMock(spec=Bot)


@pytest.mark.asyncio
async def test_open_marketplace_dispute_success(session: AsyncSession, mock_bot: AsyncMock) -> None:
    """Should open a dispute if cooldown passed and deal is paid."""
    buyer = User(telegram_id=111, username="buyer")
    seller = User(telegram_id=222, username="seller")
    session.add_all([buyer, seller])
    await session.commit()

    product = Product(
        seller_id=222, title="Test Prod", price=10.0, currency_type=CurrencyType.CRYPTO
    )
    session.add(product)
    await session.commit()

    deal_id = uuid.uuid4()
    deal = MarketplaceDeal(
        id=deal_id,
        product_id=product.id,
        buyer_id=111,
        seller_id=222,
        status=DealStatus.paid,
        amount=10.0,
        currency_type=CurrencyType.CRYPTO,
        created_at=datetime.now(UTC) - timedelta(minutes=DISPUTE_COOLDOWN_MINUTES + 5)
    )
    session.add(deal)
    await session.commit()

    result = await open_marketplace_dispute(
        session, mock_bot, deal_id=str(deal_id), initiator_id=111, reason="I didn't get it"
    )

    assert result["deal_id"] == str(deal_id)
    assert result["status"] == DealStatus.dispute
    assert result["initiator"] == "buyer"

    await session.refresh(deal)
    assert deal.status == DealStatus.dispute
    assert deal.dispute_reason == "I didn't get it"


@pytest.mark.asyncio
async def test_open_marketplace_dispute_cooldown(session: AsyncSession, mock_bot: AsyncMock) -> None:
    """Should raise ValueError if cooldown has not elapsed."""
    buyer = User(telegram_id=333, username="b3")
    seller = User(telegram_id=444, username="s4")
    session.add_all([buyer, seller])
    await session.commit()

    product = Product(
        seller_id=444, title="Test Prod", price=10.0, currency_type=CurrencyType.CRYPTO
    )
    session.add(product)
    await session.commit()

    deal_id = uuid.uuid4()
    deal = MarketplaceDeal(
        id=deal_id,
        product_id=product.id,
        buyer_id=333,
        seller_id=444,
        status=DealStatus.paid,
        amount=10.0,
        currency_type=CurrencyType.CRYPTO,
        created_at=datetime.now(UTC) - timedelta(minutes=1)
    )
    session.add(deal)
    await session.commit()

    with pytest.raises(ValueError, match="Please wait"):
        await open_marketplace_dispute(
            session, mock_bot, deal_id=str(deal_id), initiator_id=333, reason="Test"
        )


@pytest.mark.asyncio
async def test_resolve_marketplace_dispute_seller_wins(session: AsyncSession, mock_bot: AsyncMock) -> None:
    """Admin resolves dispute in favor of seller."""
    buyer = User(telegram_id=555, username="b5")
    seller = User(telegram_id=666, username="s6")
    session.add_all([buyer, seller])
    await session.commit()

    product = Product(
        seller_id=666, title="Test Prod", price=10.0, currency_type=CurrencyType.CRYPTO
    )
    session.add(product)
    await session.commit()

    deal_id = uuid.uuid4()
    deal = MarketplaceDeal(
        id=deal_id,
        product_id=product.id,
        buyer_id=555,
        seller_id=666,
        status=DealStatus.dispute,
        amount=10.0,
        currency_type=CurrencyType.CRYPTO,
    )
    session.add(deal)
    await session.commit()

    result = await resolve_marketplace_dispute(
        session, mock_bot, deal_id=str(deal_id), admin_id=999, resolution="seller", comment="Seller provided proof"
    )

    assert result["status"] == DealStatus.completed
    assert result["resolution"] == "seller"

    await session.refresh(deal)
    assert deal.status == DealStatus.completed
    assert deal.dispute_resolution == "seller"
    assert deal.dispute_resolved_by == 999
    assert deal.dispute_resolution_comment == "Seller provided proof"

    # Buyer dispute count should increase
    await session.refresh(buyer)
    assert buyer.dispute_count_buyer == 1


@pytest.mark.asyncio
async def test_resolve_marketplace_dispute_buyer_wins_xtr(session: AsyncSession, mock_bot: AsyncMock) -> None:
    """Admin resolves in favor of buyer, refunds XTR."""
    buyer = User(telegram_id=777, username="b7")
    seller = User(telegram_id=888, username="s8")
    session.add_all([buyer, seller])
    await session.commit()

    product = Product(
        seller_id=888, title="Test Prod", price=10.0, currency_type=CurrencyType.XTR
    )
    session.add(product)
    await session.commit()

    deal_id = uuid.uuid4()
    deal = MarketplaceDeal(
        id=deal_id,
        product_id=product.id,
        buyer_id=777,
        seller_id=888,
        status=DealStatus.dispute,
        amount=10.0,
        currency_type=CurrencyType.XTR,
        telegram_payment_charge_id="test_charge_id",
    )
    session.add(deal)
    await session.commit()

    with patch("services.marketplace_dispute_service._refund_to_buyer_xtr", new_callable=AsyncMock) as mock_refund:
        result = await resolve_marketplace_dispute(
            session, mock_bot, deal_id=str(deal_id), admin_id=999, resolution="buyer"
        )
        mock_refund.assert_called_once()

    assert result["status"] == DealStatus.cancelled
    assert result["resolution"] == "buyer"

    await session.refresh(deal)
    assert deal.status == DealStatus.cancelled
    assert deal.dispute_resolution == "buyer"

    # Seller dispute count should increase
    await session.refresh(seller)
    assert seller.dispute_count_seller == 1
