"""Shop service — category tree and product catalogue queries."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.product import Product, ProductCategory


class ShopService:
    """Service layer for marketplace product shop operations."""

    @staticmethod
    async def list_root_categories(session: AsyncSession) -> Sequence[ProductCategory]:
        """Fetch all root categories (categories with no parent).

        Args:
            session: Active SQLAlchemy session.

        Returns:
            A list of root ProductCategory models.
        """
        stmt = (
            select(ProductCategory)
            .where(ProductCategory.parent_id.is_(None))
            .order_by(ProductCategory.slug.asc())
        )
        result = await session.execute(stmt)
        return result.scalars().all()

    @staticmethod
    async def list_children(session: AsyncSession, parent_id: int) -> Sequence[ProductCategory]:
        """Fetch all subcategories for a given parent category.

        Args:
            session: Active SQLAlchemy session.
            parent_id: ID of the parent category.

        Returns:
            A list of subcategory ProductCategory models.
        """
        stmt = (
            select(ProductCategory)
            .where(ProductCategory.parent_id == parent_id)
            .order_by(ProductCategory.slug.asc())
        )
        result = await session.execute(stmt)
        return result.scalars().all()

    @staticmethod
    async def list_products_by_category(
        session: AsyncSession, category_id: int, page: int = 1, page_size: int = 10
    ) -> Sequence[Product]:
        """Fetch active products belonging to a specific category with pagination.

        Args:
            session: Active SQLAlchemy session.
            category_id: ID of the category.
            page: Page number (1-indexed).
            page_size: Number of items per page.

        Returns:
            A list of active Product models.
        """
        offset = (page - 1) * page_size
        stmt = (
            select(Product)
            .where(Product.category_id == category_id, Product.is_active.is_(True))
            .order_by(Product.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        result = await session.execute(stmt)
        return result.scalars().all()
