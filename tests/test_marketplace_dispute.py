"""Tests for marketplace dispute service (Phase 10).

Markers:
  - ``integration`` — requires live PostgreSQL (session fixture).
  - ``unit`` — pure logic, no I/O.

Run integration tests only:
    pytest -m integration tests/test_marketplace_dispute.py -v
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.product import CurrencyType, DealStatus, MarketplaceDeal
from services import marketplace_dispute_service

# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_deal(
    *,
    status: DealStatus = DealStatus.paid,
    currency_type: CurrencyType = CurrencyType.CRYPTO,
    age_minutes: int = 20,
    buyer_id: int = 100,
    seller_id: int = 200,
    telegram_payment_charge_id: str | None = None,
    buyer_wallet_address: str | None = "buyer_addr_xyz",
) -> MarketplaceDeal:
    """Create a MarketplaceDeal instance for testing (not persisted to DB)."""
    now = datetime.now(tz=UTC)
    deal = MarketplaceDeal()
    deal.id = uuid.uuid4()
    deal.product_id = uuid.uuid4()
    deal.buyer_id = buyer_id
    deal.seller_id = seller_id
    deal.status = status
    deal.amount = Decimal("100.00")
    deal.currency_type = currency_type
    deal.created_at = now - timedelta(minutes=age_minutes)
    deal.updated_at = now
    deal.telegram_payment_charge_id = telegram_payment_charge_id
    deal.buyer_wallet_address = buyer_wallet_address
    deal.blockchain = MagicMock()
    deal.blockchain.value = "ton"
    deal.escrow_wallet_private_key_enc = "encrypted_key"
    return deal


def _mock_begin(session: MagicMock) -> None:
    """Attach a no-op async context manager to session.begin."""
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=None)
    ctx.__aexit__ = AsyncMock(return_value=False)
    session.begin = MagicMock(return_value=ctx)


# ── Unit tests (pure logic) ───────────────────────────────────────────────────


class TestOpenDisputeValidation:
    """Unit tests for guard clauses in open_marketplace_dispute."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_wrong_status_raises(self) -> None:
        """Deal in 'created' status cannot have a dispute opened."""
        session = AsyncMock(spec=AsyncSession)
        deal = _make_deal(status=DealStatus.created)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = deal
        session.execute = AsyncMock(return_value=mock_result)
        session.begin = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=None), __aexit__=AsyncMock(return_value=False)
            )
        )

        with pytest.raises(ValueError, match="Dispute is only allowed after payment"):
            await marketplace_dispute_service.open_marketplace_dispute(
                session,
                MagicMock(),
                deal_id=str(deal.id),
                initiator_id=deal.buyer_id,
                reason="Item not received",
            )

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_third_party_raises(self) -> None:
        """User who is neither buyer nor seller cannot open a dispute."""
        session = AsyncMock(spec=AsyncSession)
        deal = _make_deal(buyer_id=100, seller_id=200)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = deal
        session.execute = AsyncMock(return_value=mock_result)
        session.begin = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=None), __aexit__=AsyncMock(return_value=False)
            )
        )

        with pytest.raises(ValueError, match="Only the buyer or seller"):
            await marketplace_dispute_service.open_marketplace_dispute(
                session,
                MagicMock(),
                deal_id=str(deal.id),
                initiator_id=999,  # third party
                reason="Fraud",
            )

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_cooldown_raises(self) -> None:
        """Dispute cannot be opened within 15 minutes of deal creation."""
        session = AsyncMock(spec=AsyncSession)
        deal = _make_deal(age_minutes=5)  # too fresh

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = deal
        session.execute = AsyncMock(return_value=mock_result)
        session.begin = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=None), __aexit__=AsyncMock(return_value=False)
            )
        )

        with pytest.raises(ValueError, match="Please wait"):
            await marketplace_dispute_service.open_marketplace_dispute(
                session,
                MagicMock(),
                deal_id=str(deal.id),
                initiator_id=deal.buyer_id,
                reason="Slow delivery",
            )

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_deal_not_found_raises(self) -> None:
        """Non-existent deal ID raises ValueError."""
        session = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=mock_result)
        session.begin = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=None), __aexit__=AsyncMock(return_value=False)
            )
        )

        with pytest.raises(ValueError, match="not found"):
            await marketplace_dispute_service.open_marketplace_dispute(
                session,
                MagicMock(),
                deal_id=str(uuid.uuid4()),
                initiator_id=100,
                reason="Test",
            )


class TestResolveDisputeValidation:
    """Unit tests for resolve_marketplace_dispute guard clauses."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_invalid_resolution_raises(self) -> None:
        """Unknown resolution value raises ValueError before touching DB."""
        session = AsyncMock(spec=AsyncSession)
        bot = AsyncMock()

        with pytest.raises(ValueError, match="Invalid resolution"):
            await marketplace_dispute_service.resolve_marketplace_dispute(
                session,
                bot,
                deal_id=str(uuid.uuid4()),
                admin_id=1,
                resolution="both",  # type: ignore[arg-type]
            )

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_not_in_dispute_status_raises(self) -> None:
        """Deal in 'completed' status cannot be resolved."""
        session = AsyncMock(spec=AsyncSession)
        bot = AsyncMock()
        deal = _make_deal(status=DealStatus.completed)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = deal
        session.execute = AsyncMock(return_value=mock_result)
        session.begin = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=None), __aexit__=AsyncMock(return_value=False)
            )
        )

        with pytest.raises(ValueError, match="not in dispute status"):
            await marketplace_dispute_service.resolve_marketplace_dispute(
                session,
                bot,
                deal_id=str(deal.id),
                admin_id=1,
                resolution="seller",
            )

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_xtr_refund_missing_charge_id_raises(self) -> None:
        """XTR refund without telegram_payment_charge_id raises ValueError."""
        deal = _make_deal(
            currency_type=CurrencyType.XTR,
            telegram_payment_charge_id=None,  # missing!
        )
        bot = AsyncMock()

        with pytest.raises(ValueError, match="no telegram_payment_charge_id"):
            await marketplace_dispute_service._refund_to_buyer_xtr(bot, deal)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_crypto_refund_missing_wallet_raises(self) -> None:
        """Crypto refund without buyer_wallet_address raises ValueError."""
        session = AsyncMock(spec=AsyncSession)
        deal = _make_deal(buyer_wallet_address=None)

        with pytest.raises(ValueError, match="no buyer_wallet_address"):
            await marketplace_dispute_service._refund_to_buyer_crypto(session, deal)
