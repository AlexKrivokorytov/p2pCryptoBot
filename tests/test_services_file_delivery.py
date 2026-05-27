"""Tests for services/file_delivery.py — secure access to purchased digital goods."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from db.models.product import CurrencyType, DealStatus, MarketplaceDeal, Product
from db.models.user import User
from services.file_delivery import FileDeliveryService

pytestmark = [pytest.mark.integration]


# ── Helpers ────────────────────────────────────────────────────────────────────


async def _make_user(session: AsyncSession, telegram_id: int) -> User:
    user = User(telegram_id=telegram_id, username=f"u{telegram_id}", first_name="T")
    session.add(user)
    await session.flush()
    return user


async def _make_deal(
    session: AsyncSession,
    buyer_id: int,
    seller_id: int,
    status: DealStatus = DealStatus.paid,
    is_digital: bool = True,
) -> uuid.UUID:
    """Create a deal and return its UUID (not the ORM object to avoid lazy load issues)."""
    product = Product(
        seller_id=seller_id,
        title="Digital Item",
        price=Decimal("10.00"),
        currency_type=CurrencyType.XTR,
        is_digital=is_digital,
    )
    session.add(product)
    await session.flush()

    deal = MarketplaceDeal(
        product_id=product.id,
        buyer_id=buyer_id,
        seller_id=seller_id,
        amount=Decimal("10.00"),
        currency_type=CurrencyType.XTR,
        status=status,
    )
    session.add(deal)
    await session.flush()
    await session.commit()
    return deal.id


# ── get_secure_link ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_secure_link_buyer_paid(session: AsyncSession) -> None:
    """Buyer can access secure link when deal is paid."""
    await _make_user(session, 1001)
    await _make_user(session, 1002)
    deal_id = await _make_deal(session, buyer_id=1001, seller_id=1002, status=DealStatus.paid)

    link = await FileDeliveryService.get_secure_link(
        session=session, deal_id=deal_id, user_id=1001
    )

    assert link == f"/api/deals/{deal_id}/download"


@pytest.mark.asyncio
async def test_get_secure_link_buyer_delivered(session: AsyncSession) -> None:
    """Buyer can access secure link when deal is delivered."""
    await _make_user(session, 1003)
    await _make_user(session, 1004)
    deal_id = await _make_deal(session, buyer_id=1003, seller_id=1004, status=DealStatus.delivered)

    link = await FileDeliveryService.get_secure_link(
        session=session, deal_id=deal_id, user_id=1003
    )

    assert "/download" in link


@pytest.mark.asyncio
async def test_get_secure_link_buyer_completed(session: AsyncSession) -> None:
    """Buyer can access secure link when deal is completed."""
    await _make_user(session, 1005)
    await _make_user(session, 1006)
    deal_id = await _make_deal(session, buyer_id=1005, seller_id=1006, status=DealStatus.completed)

    link = await FileDeliveryService.get_secure_link(
        session=session, deal_id=deal_id, user_id=1005
    )

    assert link is not None


@pytest.mark.asyncio
async def test_get_secure_link_seller_access(session: AsyncSession) -> None:
    """Seller can also access the secure link."""
    await _make_user(session, 1007)
    await _make_user(session, 1008)
    deal_id = await _make_deal(session, buyer_id=1007, seller_id=1008, status=DealStatus.paid)

    link = await FileDeliveryService.get_secure_link(
        session=session, deal_id=deal_id, user_id=1008
    )

    assert link is not None


@pytest.mark.asyncio
async def test_get_secure_link_deal_not_found(session: AsyncSession) -> None:
    """Returns 404 when deal does not exist."""
    with pytest.raises(HTTPException) as exc_info:
        await FileDeliveryService.get_secure_link(
            session=session, deal_id=uuid.uuid4(), user_id=9999
        )

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_get_secure_link_unauthorized_user(session: AsyncSession) -> None:
    """Returns 403 for a user who is neither buyer nor seller."""
    await _make_user(session, 1009)
    await _make_user(session, 1010)
    deal_id = await _make_deal(session, buyer_id=1009, seller_id=1010, status=DealStatus.paid)

    with pytest.raises(HTTPException) as exc_info:
        await FileDeliveryService.get_secure_link(
            session=session, deal_id=deal_id, user_id=9999  # stranger
        )

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_get_secure_link_buyer_unpaid_denied(session: AsyncSession) -> None:
    """Buyer cannot access the link before paying (status=created)."""
    await _make_user(session, 1011)
    await _make_user(session, 1012)
    deal_id = await _make_deal(session, buyer_id=1011, seller_id=1012, status=DealStatus.created)

    with pytest.raises(HTTPException) as exc_info:
        await FileDeliveryService.get_secure_link(
            session=session, deal_id=deal_id, user_id=1011
        )

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_get_secure_link_non_digital_product_rejected(session: AsyncSession) -> None:
    """Returns 400 for non-digital products."""
    await _make_user(session, 1013)
    await _make_user(session, 1014)
    deal_id = await _make_deal(
        session, buyer_id=1013, seller_id=1014, status=DealStatus.paid, is_digital=False
    )

    with pytest.raises(HTTPException) as exc_info:
        await FileDeliveryService.get_secure_link(
            session=session, deal_id=deal_id, user_id=1013
        )

    assert exc_info.value.status_code == 400
