"""Tests for services/marketplace_ecommerce.py — e-commerce product and deal lifecycle."""

from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.product import (
    CurrencyType,
    DealStatus,
    DiscountType,
    MarketplaceDeal,
    Product,
    PromoCode,
)
from db.models.user import User
from services.marketplace_ecommerce import MarketplaceEcommerceService

pytestmark = [pytest.mark.integration]


# ── Helpers ────────────────────────────────────────────────────────────────────


async def _make_user(session: AsyncSession, telegram_id: int, username: str = "user") -> User:
    """Create and flush a minimal User row."""
    user = User(telegram_id=telegram_id, username=username, first_name="Test")
    session.add(user)
    await session.flush()
    return user


async def _make_product(
    session: AsyncSession,
    seller_id: int,
    price: Decimal = Decimal("100.00"),
    currency_type: CurrencyType = CurrencyType.XTR,
) -> Product:
    """Create and return a flushed Product without triggering business logic."""
    product = Product(
        seller_id=seller_id,
        title="Test Digital Product",
        description="A test product",
        price=price,
        currency_type=currency_type,
        is_digital=True,
    )
    session.add(product)
    await session.flush()
    return product


# ── create_product ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_product_happy_path(session: AsyncSession) -> None:
    """create_product inserts a Product row and returns it."""
    await _make_user(session, 111)

    product = await MarketplaceEcommerceService.create_product(
        session=session,
        seller_id=111,
        title="My NFT Key",
        price=Decimal("50.00"),
        currency_type=CurrencyType.XTR,
        description="A digital good",
        is_digital=True,
    )

    assert product.id is not None
    assert product.seller_id == 111
    assert product.price == Decimal("50.00")
    assert product.currency_type == CurrencyType.XTR


@pytest.mark.asyncio
async def test_create_product_with_encrypted_content(session: AsyncSession) -> None:
    """digital_content is encrypted before storage."""
    await _make_user(session, 222)

    product = await MarketplaceEcommerceService.create_product(
        session=session,
        seller_id=222,
        title="Secret Key",
        price=Decimal("10.00"),
        currency_type=CurrencyType.XTR,
        digital_content="SUPER-SECRET-LICENSE-KEY",
    )

    # Content must be stored but not in plaintext
    assert product.digital_content is not None
    assert product.digital_content != "SUPER-SECRET-LICENSE-KEY"


@pytest.mark.asyncio
async def test_create_product_no_digital_content(session: AsyncSession) -> None:
    """digital_content is optional; None stays None."""
    await _make_user(session, 333)

    product = await MarketplaceEcommerceService.create_product(
        session=session,
        seller_id=333,
        title="Physical Product",
        price=Decimal("200.00"),
        currency_type=CurrencyType.FIAT,
        fiat_currency="USD",
        is_digital=False,
    )

    assert product.digital_content is None
    assert product.is_digital is False


# ── create_deal ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_deal_happy_path(session: AsyncSession) -> None:
    """create_deal creates a deal in 'created' status."""
    await _make_user(session, 10)
    await _make_user(session, 20)
    product = await _make_product(session, seller_id=10)

    deal = await MarketplaceEcommerceService.create_deal(
        session=session,
        product_id=product.id,
        buyer_id=20,
    )

    assert deal.id is not None
    assert deal.status == DealStatus.created
    assert deal.buyer_id == 20
    assert deal.seller_id == 10
    assert deal.amount == product.price


@pytest.mark.asyncio
async def test_create_deal_product_not_found(session: AsyncSession) -> None:
    """create_deal raises ValueError when product does not exist."""
    await _make_user(session, 30)

    with pytest.raises(ValueError, match="Product not found"):
        await MarketplaceEcommerceService.create_deal(
            session=session,
            product_id=uuid.uuid4(),
            buyer_id=30,
        )


@pytest.mark.asyncio
async def test_create_deal_self_purchase_rejected(session: AsyncSession) -> None:
    """Seller cannot buy their own product."""
    await _make_user(session, 40)
    product = await _make_product(session, seller_id=40)

    with pytest.raises(ValueError, match="cannot buy your own product"):
        await MarketplaceEcommerceService.create_deal(
            session=session,
            product_id=product.id,
            buyer_id=40,
        )


@pytest.mark.asyncio
async def test_create_deal_duplicate_rejected(session: AsyncSession) -> None:
    """Buyer cannot open a second active deal for the same product."""
    await _make_user(session, 50)
    await _make_user(session, 60)
    product = await _make_product(session, seller_id=50)

    await MarketplaceEcommerceService.create_deal(
        session=session,
        product_id=product.id,
        buyer_id=60,
    )

    with pytest.raises(ValueError, match="active deal already exists"):
        await MarketplaceEcommerceService.create_deal(
            session=session,
            product_id=product.id,
            buyer_id=60,
        )


# ── create_deal with promo codes ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_deal_with_percentage_promo(session: AsyncSession) -> None:
    """Percentage promo code reduces the deal amount correctly."""
    await _make_user(session, 70)
    await _make_user(session, 80)
    product = await _make_product(session, seller_id=70, price=Decimal("100.00"))

    promo = PromoCode(
        seller_id=70,
        code="SAVE10",
        discount_type=DiscountType.percentage,
        discount_value=Decimal("10"),
        max_uses=None,
        current_uses=0,
    )
    session.add(promo)
    await session.flush()

    deal = await MarketplaceEcommerceService.create_deal(
        session=session,
        product_id=product.id,
        buyer_id=80,
        promo_code_str="SAVE10",
    )

    assert deal.amount == Decimal("90.00")
    assert deal.original_amount == Decimal("100.00")


@pytest.mark.asyncio
async def test_create_deal_with_fixed_promo(session: AsyncSession) -> None:
    """Fixed promo code subtracts a flat amount from the deal."""
    await _make_user(session, 90)
    await _make_user(session, 100)
    product = await _make_product(session, seller_id=90, price=Decimal("50.00"))

    promo = PromoCode(
        seller_id=90,
        code="FLAT5",
        discount_type=DiscountType.fixed,
        discount_value=Decimal("5"),
        current_uses=0,
    )
    session.add(promo)
    await session.flush()

    deal = await MarketplaceEcommerceService.create_deal(
        session=session,
        product_id=product.id,
        buyer_id=100,
        promo_code_str="FLAT5",
    )

    assert deal.amount == Decimal("45.00")


@pytest.mark.asyncio
async def test_create_deal_invalid_promo_code(session: AsyncSession) -> None:
    """Invalid promo code raises ValueError."""
    await _make_user(session, 110)
    await _make_user(session, 120)
    product = await _make_product(session, seller_id=110)

    with pytest.raises(ValueError, match="Invalid promo code"):
        await MarketplaceEcommerceService.create_deal(
            session=session,
            product_id=product.id,
            buyer_id=120,
            promo_code_str="DOESNOTEXIST",
        )


@pytest.mark.asyncio
async def test_create_deal_promo_max_uses_exhausted(session: AsyncSession) -> None:
    """Promo code that has hit max_uses is rejected."""
    await _make_user(session, 130)
    await _make_user(session, 140)
    product = await _make_product(session, seller_id=130)

    promo = PromoCode(
        seller_id=130,
        code="USED",
        discount_type=DiscountType.percentage,
        discount_value=Decimal("10"),
        max_uses=1,
        current_uses=1,
    )
    session.add(promo)
    await session.flush()

    with pytest.raises(ValueError, match="usage limit reached"):
        await MarketplaceEcommerceService.create_deal(
            session=session,
            product_id=product.id,
            buyer_id=140,
            promo_code_str="USED",
        )


# ── deliver_deal ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_deliver_deal_happy_path(session: AsyncSession) -> None:
    """deliver_deal transitions status from paid → delivered."""
    await _make_user(session, 150)
    await _make_user(session, 160)
    product = await _make_product(session, seller_id=150)

    deal = MarketplaceDeal(
        product_id=product.id,
        buyer_id=160,
        seller_id=150,
        amount=Decimal("100.00"),
        currency_type=CurrencyType.XTR,
        status=DealStatus.paid,
    )
    session.add(deal)
    await session.flush()

    await MarketplaceEcommerceService.deliver_deal(session=session, deal=deal)

    assert deal.status == DealStatus.delivered


@pytest.mark.asyncio
async def test_deliver_deal_wrong_status_raises(session: AsyncSession) -> None:
    """deliver_deal raises ValueError if deal is not paid."""
    await _make_user(session, 170)
    await _make_user(session, 180)
    product = await _make_product(session, seller_id=170)

    deal = MarketplaceDeal(
        product_id=product.id,
        buyer_id=180,
        seller_id=170,
        amount=Decimal("100.00"),
        currency_type=CurrencyType.XTR,
        status=DealStatus.created,
    )
    session.add(deal)
    await session.flush()

    with pytest.raises(ValueError, match="must be paid"):
        await MarketplaceEcommerceService.deliver_deal(session=session, deal=deal)


# ── complete_deal ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_complete_deal_happy_path(session: AsyncSession) -> None:
    """complete_deal transitions status from delivered → completed."""
    await _make_user(session, 190)
    await _make_user(session, 200)
    product = await _make_product(session, seller_id=190)

    deal = MarketplaceDeal(
        product_id=product.id,
        buyer_id=200,
        seller_id=190,
        amount=Decimal("100.00"),
        currency_type=CurrencyType.FIAT,
        status=DealStatus.delivered,
    )
    session.add(deal)
    await session.flush()

    with patch("tasks.payout_worker.process_payout_to_seller", new_callable=AsyncMock):
        await MarketplaceEcommerceService.complete_deal(session=session, deal=deal)

    assert deal.status == DealStatus.completed


@pytest.mark.asyncio
async def test_complete_deal_wrong_status_raises(session: AsyncSession) -> None:
    """complete_deal raises ValueError if deal is not delivered."""
    await _make_user(session, 210)
    await _make_user(session, 220)
    product = await _make_product(session, seller_id=210)

    deal = MarketplaceDeal(
        product_id=product.id,
        buyer_id=220,
        seller_id=210,
        amount=Decimal("100.00"),
        currency_type=CurrencyType.XTR,
        status=DealStatus.paid,
    )
    session.add(deal)
    await session.flush()

    with pytest.raises(ValueError, match="must be delivered"):
        await MarketplaceEcommerceService.complete_deal(session=session, deal=deal)


# ── get_deal ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_deal_returns_deal(session: AsyncSession) -> None:
    """get_deal returns the deal by ID with product loaded."""
    await _make_user(session, 230)
    await _make_user(session, 240)
    product = await _make_product(session, seller_id=230)

    deal = MarketplaceDeal(
        product_id=product.id,
        buyer_id=240,
        seller_id=230,
        amount=Decimal("100.00"),
        currency_type=CurrencyType.XTR,
        status=DealStatus.created,
    )
    session.add(deal)
    await session.flush()

    fetched = await MarketplaceEcommerceService.get_deal(session=session, deal_id=deal.id)

    assert fetched is not None
    assert fetched.id == deal.id


@pytest.mark.asyncio
async def test_get_deal_returns_none_for_unknown(session: AsyncSession) -> None:
    """get_deal returns None when deal does not exist."""
    result = await MarketplaceEcommerceService.get_deal(session=session, deal_id=uuid.uuid4())
    assert result is None
