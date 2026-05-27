"""Tests for ProductCategory model, shop service, and seeding."""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.product import CurrencyType, Product, ProductCategory
from db.models.user import User
from init_db import _seed_categories
from services.shop_service import ShopService

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def test_category_slug_uniqueness(session: AsyncSession) -> None:
    """Test that category slugs must be unique.

    Args:
        session: Active SQLAlchemy session.
    """
    cat1 = ProductCategory(slug="electronics", parent_id=None)
    session.add(cat1)
    await session.flush()

    cat2 = ProductCategory(slug="electronics", parent_id=None)
    session.add(cat2)

    with pytest.raises(IntegrityError):
        await session.flush()


async def test_seeding_categories(session: AsyncSession) -> None:
    """Test that _seed_categories seeds exactly 30 categories (8 root + 22 children).

    Args:
        session: Active SQLAlchemy session.
    """
    # Seed the database
    await _seed_categories(session)
    await session.commit()

    # Query all categories
    stmt = select(ProductCategory)
    result = await session.execute(stmt)
    categories = result.scalars().all()

    # Total should be 30 categories
    assert len(categories) == 30

    # Roots should be 8
    roots = [c for c in categories if c.parent_id is None]
    assert len(roots) == 8

    # Children should be 22
    children = [c for c in categories if c.parent_id is not None]
    assert len(children) == 22

    # Check some specific links
    games_cat = next(c for c in roots if c.slug == "games")
    game_currency = next(c for c in children if c.slug == "game_currency")
    assert game_currency.parent_id == games_cat.id


async def test_shop_service_list_root_categories(session: AsyncSession) -> None:
    """Test retrieving root categories via ShopService.

    Args:
        session: Active SQLAlchemy session.
    """
    await _seed_categories(session)
    await session.flush()

    roots = await ShopService.list_root_categories(session)
    assert len(roots) == 8
    assert all(r.parent_id is None for r in roots)
    # Check alphabet sorting
    slugs = [r.slug for r in roots]
    assert slugs == sorted(slugs)


async def test_shop_service_list_children(session: AsyncSession) -> None:
    """Test retrieving child subcategories via ShopService.

    Args:
        session: Active SQLAlchemy session.
    """
    await _seed_categories(session)
    await session.flush()

    # Find games
    games_result = await session.execute(
        select(ProductCategory).where(ProductCategory.slug == "games")
    )
    games_cat = games_result.scalar_one()

    children = await ShopService.list_children(session, games_cat.id)
    assert len(children) == 4
    assert all(c.parent_id == games_cat.id for c in children)
    assert {c.slug for c in children} == {
        "game_currency",
        "game_items",
        "game_accounts",
        "game_services",
    }


async def test_shop_service_list_products_by_category(session: AsyncSession) -> None:
    """Test listing products by category with pagination.

    Args:
        session: Active SQLAlchemy session.
    """
    await _seed_categories(session)
    await session.flush()

    # Create a seller user
    seller = User(telegram_id=9876, username="shop_seller", first_name="ShopSeller")
    session.add(seller)

    # Get a category
    games_cat_res = await session.execute(
        select(ProductCategory).where(ProductCategory.slug == "game_currency")
    )
    games_cat = games_cat_res.scalar_one()

    # Ensure list_products_by_category returns empty when no products exist
    empty_products = await ShopService.list_products_by_category(session, games_cat.id)
    assert len(empty_products) == 0

    # Create multiple products
    for i in range(15):
        product = Product(
            seller_id=seller.telegram_id,
            title=f"Game Gold Pack {i}",
            price=Decimal("10.00"),
            currency_type=CurrencyType.XTR,
            category_id=games_cat.id,
            is_active=True,
        )
        session.add(product)
    await session.flush()

    # Retrieve page 1 (default 10 items)
    page1 = await ShopService.list_products_by_category(session, games_cat.id, page=1, page_size=10)
    assert len(page1) == 10

    # Retrieve page 2
    page2 = await ShopService.list_products_by_category(session, games_cat.id, page=2, page_size=10)
    assert len(page2) == 5

    # Retrieve with inactive product
    inactive_product = Product(
        seller_id=seller.telegram_id,
        title="Inactive Gold",
        price=Decimal("5.00"),
        currency_type=CurrencyType.XTR,
        category_id=games_cat.id,
        is_active=False,
    )
    session.add(inactive_product)
    await session.flush()

    # Active products on page 2 should still be 5
    page2_active = await ShopService.list_products_by_category(
        session, games_cat.id, page=2, page_size=10
    )
    assert len(page2_active) == 5


async def test_product_category_ondelete_set_null(session: AsyncSession) -> None:
    """Test that deleting a category sets product.category_id to NULL.

    Args:
        session: Active SQLAlchemy session.
    """
    # Create seller
    seller = User(telegram_id=9877, username="set_null_seller", first_name="SetNull")
    session.add(seller)

    # Create a category
    cat = ProductCategory(slug="temp_category", parent_id=None)
    session.add(cat)
    await session.flush()

    # Create a product in that category
    product = Product(
        seller_id=seller.telegram_id,
        title="Temp Product",
        price=Decimal("1.00"),
        currency_type=CurrencyType.XTR,
        category_id=cat.id,
        is_active=True,
    )
    session.add(product)
    await session.flush()

    assert product.category_id == cat.id

    # Delete the category
    await session.delete(cat)
    await session.flush()

    # Verify category is deleted but product survives with category_id = None
    stmt_cat = select(ProductCategory).where(ProductCategory.id == cat.id)
    cat_check = (await session.execute(stmt_cat)).scalar_one_or_none()
    assert cat_check is None

    stmt_prod = select(Product).where(Product.id == product.id)
    prod_check = (await session.execute(stmt_prod)).scalar_one()
    assert prod_check.category_id is None
