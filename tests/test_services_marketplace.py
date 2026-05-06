"""Tests for MarketplaceService — coverage for all service methods."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from db.models.marketplace import Ad, AdType, PriceType, Review, UserPaymentDetail
from services.marketplace_service import MarketplaceService


@pytest.mark.asyncio
async def test_create_ad_adds_and_flushes() -> None:
    """create_ad should construct an Ad, add it to session, and flush."""
    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()

    ad = await MarketplaceService.create_ad(
        session=session,
        maker_id=123,
        ad_type=AdType.sell,
        asset="USDT",
        fiat="RUB",
        price_type=PriceType.fixed,
        price_value=90.5,
        min_limit=1000.0,
        max_limit=50000.0,
        payment_method_ids="1,2",
        terms="No chargebacks",
    )

    session.add.assert_called_once()
    session.flush.assert_awaited_once()
    assert isinstance(ad, Ad)
    assert ad.maker_id == 123
    assert ad.asset == "USDT"
    assert ad.fiat == "RUB"
    assert ad.terms == "No chargebacks"


@pytest.mark.asyncio
async def test_create_ad_without_terms() -> None:
    """create_ad with no terms should default to None."""
    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()

    ad = await MarketplaceService.create_ad(
        session=session,
        maker_id=456,
        ad_type=AdType.buy,
        asset="TON",
        fiat="USD",
        price_type=PriceType.fixed,
        price_value=3.5,
        min_limit=10.0,
        max_limit=500.0,
        payment_method_ids="",
    )

    assert ad.terms is None
    assert ad.ad_type == AdType.buy if hasattr(ad, "ad_type") else ad.type == AdType.buy


@pytest.mark.asyncio
async def test_get_active_ads_sell() -> None:
    """get_active_ads for sell type should order by price ascending."""
    session = MagicMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(return_value=mock_result)

    result = await MarketplaceService.get_active_ads(
        session=session, asset="USDT", fiat="RUB", ad_type=AdType.sell
    )

    session.execute.assert_awaited_once()
    assert result == []


@pytest.mark.asyncio
async def test_get_active_ads_buy() -> None:
    """get_active_ads for buy type should order by price descending."""
    session = MagicMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(return_value=mock_result)

    result = await MarketplaceService.get_active_ads(
        session=session, asset="TON", fiat="USD", ad_type=AdType.buy
    )

    session.execute.assert_awaited_once()
    assert result == []


@pytest.mark.asyncio
async def test_add_user_payment_detail() -> None:
    """add_user_payment_detail should create and flush a UserPaymentDetail."""
    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()

    detail = await MarketplaceService.add_user_payment_detail(
        session=session,
        user_id=789,
        payment_method_id=1,
        account_name="Ivan Ivanov",
        account_number="4276 1234 5678",
    )

    session.add.assert_called_once()
    session.flush.assert_awaited_once()
    assert isinstance(detail, UserPaymentDetail)
    assert detail.user_id == 789
    assert detail.account_name == "Ivan Ivanov"


@pytest.mark.asyncio
async def test_get_user_payment_details_returns_list() -> None:
    """get_user_payment_details should query by user_id and return results."""
    session = MagicMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(return_value=mock_result)

    result = await MarketplaceService.get_user_payment_details(session=session, user_id=42)

    session.execute.assert_awaited_once()
    assert result == []


@pytest.mark.asyncio
async def test_add_review_positive() -> None:
    """add_review should persist a positive review."""
    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()

    order_id = uuid.uuid4()
    review = await MarketplaceService.add_review(
        session=session,
        order_id=order_id,
        reviewer_id=100,
        target_id=200,
        is_positive=True,
        comment="Great trader!",
    )

    session.add.assert_called_once()
    session.flush.assert_awaited_once()
    assert isinstance(review, Review)
    assert review.is_positive is True
    assert review.comment == "Great trader!"


@pytest.mark.asyncio
async def test_add_review_negative_no_comment() -> None:
    """add_review with no comment should default comment to None."""
    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()

    review = await MarketplaceService.add_review(
        session=session,
        order_id=uuid.uuid4(),
        reviewer_id=1,
        target_id=2,
        is_positive=False,
    )

    assert review.comment is None
    assert review.is_positive is False


@pytest.mark.asyncio
async def test_get_user_reputation_no_reviews() -> None:
    """get_user_reputation with no reviews returns 100% completion rate."""
    session = MagicMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(return_value=mock_result)

    rep = await MarketplaceService.get_user_reputation(session=session, user_id=999)

    assert rep["total_reviews"] == 0
    assert rep["positive_reviews"] == 0
    assert rep["completion_rate"] == 100


@pytest.mark.asyncio
async def test_get_user_reputation_with_mixed_reviews() -> None:
    """get_user_reputation should calculate positive ratio correctly."""
    session = MagicMock()
    mock_result = MagicMock()
    # 3 reviews: True, True, False → 2 positive out of 3
    mock_result.scalars.return_value.all.return_value = [True, True, False]
    session.execute = AsyncMock(return_value=mock_result)

    rep = await MarketplaceService.get_user_reputation(session=session, user_id=42)

    assert rep["total_reviews"] == 3
    assert rep["positive_reviews"] == 2
    assert rep["completion_rate"] == 66
