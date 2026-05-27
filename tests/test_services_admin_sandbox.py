"""Integration tests for services/admin_sandbox_service.py."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.admin import AdminAuditLog
from db.models.order import Order, OrderStatus, OrderType, SupportedAsset
from db.models.user import User
from db.models.wallet import UserWallet
from services.admin_sandbox_service import (
    activate_license_bypass,
    force_order_status,
    inject_test_balance,
    log_admin_action,
)

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_log_admin_action(session: AsyncSession) -> None:
    """log_admin_action creates an AdminAuditLog entry."""
    await log_admin_action(
        session,
        admin_id=999,
        action="test_action",
        target_id="123",
        details={"key": "value"},
    )
    await session.commit()

    stmt = select(AdminAuditLog).where(AdminAuditLog.admin_id == 999)
    res = await session.execute(stmt)
    log_entry = res.scalar_one()

    assert log_entry.action == "test_action"
    assert log_entry.target_id == "123"
    assert log_entry.details == {"key": "value"}


@pytest.mark.asyncio
async def test_inject_test_balance(session: AsyncSession) -> None:
    """inject_test_balance creates or updates UserWallet and logs action."""
    user = User(telegram_id=1010, username="testuser")
    session.add(user)
    await session.commit()

    # Initial injection
    await inject_test_balance(session, admin_id=999, user_id=1010, amount=500.0, asset="USDT")

    # Check wallet was created
    stmt = select(UserWallet).where(UserWallet.user_id == 1010)
    res = await session.execute(stmt)
    wallet = res.scalar_one()
    assert wallet.chain == "evm"
    assert "MOCK_USDT" in wallet.address

    # Check audit log
    log_stmt = select(AdminAuditLog).where(
        AdminAuditLog.admin_id == 999, AdminAuditLog.action == "inject_balance"
    )
    log_res = await session.execute(log_stmt)
    log_entry = log_res.scalars().first()
    assert log_entry is not None
    assert log_entry.details["amount"] == 500.0
    assert log_entry.details["asset"] == "USDT"


@pytest.mark.asyncio
async def test_activate_license_bypass_new(session: AsyncSession) -> None:
    """activate_license_bypass creates a new active license."""
    user = User(telegram_id=2020, username="b2b_user")
    session.add(user)
    await session.commit()

    lic = await activate_license_bypass(session, admin_id=999, user_id=2020, days=30)

    assert lic.owner_id == 2020
    assert lic.is_active is True
    assert lic.expires_at > datetime.now(UTC)


@pytest.mark.asyncio
async def test_force_order_status(session: AsyncSession) -> None:
    """force_order_status updates the status of an existing order."""
    user1 = User(telegram_id=3030, username="maker")
    user2 = User(telegram_id=4040, username="taker")
    session.add_all([user1, user2])
    await session.commit()

    order_id = uuid.uuid4()
    order = Order(
        id=order_id,
        maker_id=3030,
        taker_id=4040,
        asset=SupportedAsset.USDT,
        fiat_currency="USD",
        fiat_amount=100.0,
        amount=100.0,
        order_type=OrderType.sell_crypto,
        status=OrderStatus.pending_funding,
    )
    session.add(order)
    await session.commit()

    await force_order_status(session, admin_id=999, order_id=str(order_id), new_status="completed")

    # Verify status changed
    stmt = select(Order).where(Order.id == order_id)
    res = await session.execute(stmt)
    updated_order = res.scalar_one()
    assert updated_order.status == OrderStatus.completed

    # Verify audit log
    log_stmt = select(AdminAuditLog).where(
        AdminAuditLog.admin_id == 999, AdminAuditLog.action == "force_order_status"
    )
    log_res = await session.execute(log_stmt)
    log_entry = log_res.scalars().first()
    assert log_entry is not None
    assert log_entry.target_id == str(order_id)
    assert log_entry.details["old_status"] == "pending_funding"
    assert log_entry.details["new_status"] == "completed"
