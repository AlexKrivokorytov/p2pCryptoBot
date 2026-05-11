"""Extended tests for b2b_service."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.user import User
from services import b2b_service


@pytest.mark.asyncio
async def test_process_ton_payment_already_paid(session: AsyncSession):
    # Setup
    user = User(telegram_id=111, username="test")
    session.add(user)
    await session.commit()

    invoice = await b2b_service.create_ton_invoice(session, user_id=111, amount_ton=10.0)
    memo = invoice["memo"]

    # Mark as paid manually
    from sqlalchemy import select

    from db.models.b2b import TONInvoice

    res = await session.execute(select(TONInvoice).where(TONInvoice.memo == memo))
    inv_obj = res.scalar_one()
    inv_obj.status = "paid"
    await session.commit()

    # Try processing again
    result = await b2b_service.process_ton_payment(
        session, memo=memo, tx_hash="hash", amount_nanotons=10_000_000_000, utime=123
    )
    assert result is False


@pytest.mark.asyncio
async def test_process_ton_payment_not_found(session: AsyncSession):
    result = await b2b_service.process_ton_payment(
        session, memo="NON_EXISTENT", tx_hash="hash", amount_nanotons=10, utime=123
    )
    assert result is False


@pytest.mark.asyncio
async def test_create_b2b_license_idempotency(session: AsyncSession):
    user = User(telegram_id=222, username="test2")
    session.add(user)
    await session.commit()

    # First call
    lic1 = await b2b_service.create_b2b_license(session, user_id=222, charge_id="charge_uniq")

    # Second call with same charge_id
    lic2 = await b2b_service.create_b2b_license(session, user_id=222, charge_id="charge_uniq")

    assert lic1["license_id"] == lic2["license_id"]


@pytest.mark.asyncio
async def test_get_active_license_expired(session: AsyncSession):
    user = User(telegram_id=333, username="test3")
    session.add(user)
    await session.commit()

    from datetime import datetime, timedelta

    from db.models.b2b import B2BLicense

    # Create expired license
    lic = B2BLicense(
        owner_id=333,
        expires_at=datetime.utcnow() - timedelta(days=1),
        is_active=True,
        telegram_payment_charge_id="old_charge",
    )
    session.add(lic)
    await session.commit()

    active = await b2b_service.get_active_license(session, 333)
    assert active is None
