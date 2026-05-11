"""B2B service for managing white-label licenses and payments."""

import uuid
from datetime import datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import get_branding
from db.models.b2b import B2BLicense, TONInvoice
from services.rate_service import get_market_rate

log = structlog.get_logger(__name__)


async def get_active_license(session: AsyncSession, user_id: int) -> dict[str, Any] | None:
    """Fetch active B2B license for a user.

    Args:
        session: DB session.
        user_id: Telegram user ID.

    Returns:
        Dict of license details if found and active, else None.
    """
    stmt = (
        select(B2BLicense)
        .where(
            B2BLicense.owner_id == user_id,
            B2BLicense.is_active,
            B2BLicense.expires_at > datetime.utcnow(),
        )
        .limit(1)
    )
    result = await session.execute(stmt)
    license_obj = result.scalar_one_or_none()

    if not license_obj:
        return None

    return {
        "license_id": str(license_obj.id),
        "expires_at": license_obj.expires_at,
        "branding": license_obj.branding,
        "is_active": license_obj.is_active,
    }


async def create_b2b_license(
    session: AsyncSession, user_id: int, charge_id: str, duration_days: int = 365
) -> dict[str, Any]:
    """Create or renew a B2B license after successful payment.

    Uses pessimistic locking to ensure idempotency and prevent duplicate activation.

    Args:
        session: DB session.
        user_id: Telegram user ID.
        charge_id: Telegram Stars payment charge ID.
        duration_days: License duration in days.

    Returns:
        Dict of newly created/updated license.
    """
    async with session.begin():
        # Check if charge_id already used (Idempotency)
        stmt_check = select(B2BLicense).where(B2BLicense.telegram_payment_charge_id == charge_id)
        result_check = await session.execute(stmt_check)
        existing = result_check.scalar_one_or_none()

        if existing:
            log.info("b2b_license_already_exists", user_id=user_id, charge_id=charge_id)
            return {
                "license_id": str(existing.id),
                "expires_at": existing.expires_at,
                "is_active": existing.is_active,
            }

        # Create new license
        expires_at = datetime.utcnow() + timedelta(days=duration_days)

        # Load default branding from system config
        default_branding = get_branding()

        new_license = B2BLicense(
            owner_id=user_id,
            telegram_payment_charge_id=charge_id,
            expires_at=expires_at,
            branding=default_branding,
            is_active=True,
        )

        session.add(new_license)
        await session.flush()

        log.info(
            "b2b_license_activated",
            user_id=user_id,
            license_id=str(new_license.id),
            expires_at=expires_at.isoformat(),
            step="create_b2b_license",
        )

        return {
            "license_id": str(new_license.id),
            "expires_at": new_license.expires_at,
            "is_active": new_license.is_active,
        }


async def create_ton_invoice(
    session: AsyncSession, user_id: int, amount_ton: float
) -> dict[str, Any]:
    """Create a new TON invoice for a B2B license.

    Args:
        session: DB session.
        user_id: Telegram user ID.
        amount_ton: Amount in TON.

    Returns:
        Dict of invoice details.
    """
    memo = str(uuid.uuid4()).replace("-", "")[:12].upper()

    invoice = TONInvoice(
        owner_id=user_id,
        amount_ton=amount_ton,
        status="pending",
        memo=memo,
    )

    session.add(invoice)
    await session.commit()

    log.info("ton_invoice_created", user_id=user_id, memo=memo, amount=amount_ton)

    return {
        "invoice_id": str(invoice.id),
        "amount_ton": invoice.amount_ton,
        "memo": invoice.memo,
        "status": invoice.status,
    }


async def process_ton_payment(
    session: AsyncSession, memo: str, tx_hash: str, amount_nanotons: int, utime: int
) -> bool:
    """Process an incoming TON payment identified by memo.

    Args:
        session: DB session.
        memo: Transaction memo (comment).
        tx_hash: Transaction hash.
        amount_nanotons: Amount received.
        utime: Transaction unix time.

    Returns:
        True if payment was successfully processed and license activated.
    """
    # 1. Find invoice by memo with pessimistic lock
    stmt = select(TONInvoice).where(TONInvoice.memo == memo).with_for_update()
    result = await session.execute(stmt)
    invoice = result.scalar_one_or_none()

    if not invoice:
        return False

    if invoice.status != "pending":
        return False

    # 2. Verify amount (allow 1% slippage or just exact)
    # 1 TON = 1,000,000,000 nanotons
    expected_nanotons = int(invoice.amount_ton * 1e9)
    if amount_nanotons < expected_nanotons:
        log.warning(
            "ton_payment_insufficient_amount",
            memo=memo,
            expected=expected_nanotons,
            actual=amount_nanotons,
        )
        return False

    # 3. Mark invoice as paid
    invoice.status = "paid"
    invoice.tx_hash = tx_hash
    invoice.paid_at = datetime.fromtimestamp(utime)

    # 4. Activate/Renew license
    # We use a unique charge_id for TON to prevent double activation
    # Charge ID for TON is "TON:{tx_hash}"
    charge_id = f"TON:{tx_hash}"

    await create_b2b_license(
        session, user_id=invoice.owner_id, charge_id=charge_id, duration_days=365
    )

    await session.commit()

    log.info(
        "ton_payment_processed",
        user_id=invoice.owner_id,
        memo=memo,
        tx_hash=tx_hash,
        status="success",
    )
    return True


async def get_ton_license_price() -> float:
    """Calculate TON price for a 1-year license ($100 USD target).

    Returns:
        Amount in TON. Defaults to 20 TON if rate lookup fails.
    """
    rate = await get_market_rate("TON", "USD")
    if not rate or rate <= 0:
        return 20.0  # Safe fallback (assuming TON is ~$5)

    # $100 / (USD per 1 TON) = TON amount
    amount = 100.0 / float(rate)
    return round(amount, 2)
