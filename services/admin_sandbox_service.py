"""Service for administrative debug and testing operations with audit logging."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.admin import AdminAuditLog
from db.models.b2b import B2BLicense
from db.models.order import Order
from db.models.user import User


async def log_admin_action(
    session: AsyncSession,
    admin_id: int,
    action: str,
    target_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Record an administrative action in the audit log."""
    log_entry = AdminAuditLog(
        admin_id=admin_id, action=action, target_id=target_id, details=details or {}
    )
    session.add(log_entry)
    # We do NOT commit here to allow atomic operations in the caller


async def inject_test_balance(
    session: AsyncSession, admin_id: int, user_id: int, amount: float, asset: str = "USDT"
) -> None:
    """Instantly update user balance for testing (Sandbox only)."""
    stmt = select(User).where(User.telegram_id == user_id).with_for_update()
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if user:
        from db.models.wallet import UserWallet

        wallet_stmt = (
            select(UserWallet)
            .where(
                UserWallet.user_id == user_id,
                UserWallet.chain == ("ton" if asset == "TON" else "evm"),
            )
            .with_for_update()
        )
        w_res = await session.execute(wallet_stmt)
        wallet = w_res.scalar_one_or_none()

        if not wallet:
            wallet = UserWallet(
                user_id=user_id,
                address=f"MOCK_{asset}_{uuid.uuid4().hex[:8]}",
                chain="ton" if asset == "TON" else "evm",
                encrypted_private_key="MOCK",
            )
            session.add(wallet)

        # Log the action
        await log_admin_action(
            session,
            admin_id=admin_id,
            action="inject_balance",
            target_id=str(user_id),
            details={"amount": amount, "asset": asset},
        )
        await session.commit()


async def activate_license_bypass(
    session: AsyncSession, admin_id: int, user_id: int, days: int = 365
) -> B2BLicense:
    """Manually activate a B2B license for a user without payment (Sandbox)."""
    stmt = select(B2BLicense).where(B2BLicense.owner_id == user_id).with_for_update()
    result = await session.execute(stmt)
    lic = result.scalar_one_or_none()

    expires_at = datetime.now(UTC) + timedelta(days=days)

    if lic:
        lic.is_active = True
        lic.expires_at = expires_at
    else:
        lic = B2BLicense(owner_id=user_id, is_active=True, expires_at=expires_at, branding={})
        session.add(lic)

    await log_admin_action(
        session,
        admin_id=admin_id,
        action="activate_license_bypass",
        target_id=str(user_id),
        details={"days": days, "expires_at": expires_at.isoformat()},
    )

    await session.commit()
    return lic


async def force_order_status(
    session: AsyncSession, admin_id: int, order_id: str, new_status: str
) -> None:
    """Force an order into a specific status for testing (Sandbox)."""
    stmt = select(Order).where(Order.id == order_id).with_for_update()
    result = await session.execute(stmt)
    order = result.scalar_one_or_none()

    if order:
        old_status = order.status
        order.status = new_status

        await log_admin_action(
            session,
            admin_id=admin_id,
            action="force_order_status",
            target_id=order_id,
            details={"old_status": old_status, "new_status": new_status},
        )
        await session.commit()
