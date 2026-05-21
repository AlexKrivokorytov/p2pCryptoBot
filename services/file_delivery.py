"""Service for secure file delivery of digital marketplace products."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from fastapi import HTTPException
from sqlalchemy import select

from db.models.product import DealStatus, MarketplaceDeal

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class FileDeliveryService:
    """Service to handle secure access to purchased digital assets."""

    UPLOAD_DIR = "/app/uploads"

    @classmethod
    async def get_secure_link(cls, session: AsyncSession, deal_id: uuid.UUID, user_id: int) -> str:
        """Verify purchase and return a secure access path.

        In a production environment, this would generate a presigned S3 URL
         or a token-protected internal redirect. For now, it verifies
         ownership and returns the relative path.
        """
        stmt = select(MarketplaceDeal).where(MarketplaceDeal.id == deal_id)
        result = await session.execute(stmt)
        deal = result.scalar_one_or_none()

        if not deal:
            raise HTTPException(status_code=404, detail="Deal not found")

        # 1. Access Control: Only buyer or seller can access
        if user_id not in (deal.buyer_id, deal.seller_id):
            raise HTTPException(status_code=403, detail="Unauthorized access to this deal's assets")

        # 2. Status Check: Must be paid/delivered/completed for buyer to access
        if user_id == deal.buyer_id and deal.status not in (
            DealStatus.paid,
            DealStatus.delivered,
            DealStatus.completed,
        ):
            raise HTTPException(status_code=403, detail="Payment required to access digital goods")

        # 3. Product check
        if not deal.product.is_digital:
            raise HTTPException(status_code=400, detail="This deal is not for a digital product")

        # TODO: Implement token-based secure serving or presigned URLs
        # For now, return a placeholder or specific asset path if stored
        return f"/api/deals/{deal.id}/download"
