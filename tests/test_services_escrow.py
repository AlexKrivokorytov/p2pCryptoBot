"""Tests for escrow service: release, refund — full coverage."""

from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.order import Order, OrderStatus, OrderType
from db.models.user import User
from services import escrow_service

pytestmark = [pytest.mark.integration, pytest.mark.unit]

# ── Helpers ────────────────────────────────────────────────────────────────────


async def _create_user(session: AsyncSession, telegram_id: int, username: str) -> User:
    async with session.begin():
        existing = await session.get(User, telegram_id)
        if existing:
            return existing
        user = User(telegram_id=telegram_id, username=username, first_name=username)
        session.add(user)
        return user


async def _create_order(
    session: AsyncSession,
    status: OrderStatus,
    maker_id: int = 501,
    taker_id: int = 502,
    order_type: str = OrderType.sell_crypto,
) -> Order:
    """Create a test order with FK-safe users."""
    await _create_user(session, maker_id, f"maker_{maker_id}")
    await _create_user(session, taker_id, f"taker_{taker_id}")
    async with session.begin():
        order = Order(
            id=uuid.uuid4(),
            maker_id=maker_id,
            taker_id=taker_id,
            order_type=order_type,
            asset="USDT",
            amount=Decimal("100.0"),
            fiat_currency="USD",
            fiat_amount=Decimal("100.0"),
            payment_method="Sberbank",
            status=status,
            spend_id=str(uuid.uuid4()),
            total_fee=Decimal("1.0"),
            fiat_confirmed=(status == OrderStatus.escrow_held),
        )
        session.add(order)
        return order


def _mock_crypto_pay() -> MagicMock:
    cp = MagicMock()
    cp.transfer = AsyncMock(return_value={"transfer_id": "tx_test", "status": "completed"})
    return cp


# ── release_escrow ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_release_escrow_sell_crypto(session: AsyncSession) -> None:
    """release_escrow sends crypto to taker_id for sell_crypto orders."""
    order = await _create_order(session, OrderStatus.escrow_held, order_type=OrderType.sell_crypto)
    crypto_pay = _mock_crypto_pay()

    result = await escrow_service.release_escrow(session, crypto_pay, order_id=str(order.id))

    assert result["status"] == OrderStatus.completed
    crypto_pay.transfer.assert_called_once()
    call_kwargs = crypto_pay.transfer.call_args[1]
    assert call_kwargs["user_id"] == order.taker_id


@pytest.mark.asyncio
async def test_release_escrow_buy_crypto(session: AsyncSession) -> None:
    """release_escrow sends crypto to maker_id for buy_crypto orders."""
    order = await _create_order(
        session,
        OrderStatus.escrow_held,
        maker_id=510,
        taker_id=511,
        order_type=OrderType.buy_crypto,
    )
    crypto_pay = _mock_crypto_pay()

    result = await escrow_service.release_escrow(session, crypto_pay, order_id=str(order.id))

    assert result["status"] == OrderStatus.completed
    call_kwargs = crypto_pay.transfer.call_args[1]
    assert call_kwargs["user_id"] == order.maker_id


@pytest.mark.asyncio
async def test_release_escrow_force_from_dispute(session: AsyncSession) -> None:
    """release_escrow with force=True works from dispute status."""
    order = await _create_order(session, OrderStatus.dispute)
    crypto_pay = _mock_crypto_pay()

    result = await escrow_service.release_escrow(
        session, crypto_pay, order_id=str(order.id), force=True
    )

    assert result["status"] == OrderStatus.completed


@pytest.mark.asyncio
async def test_release_escrow_not_found(session: AsyncSession) -> None:
    """release_escrow raises ValueError for unknown order_id."""
    crypto_pay = _mock_crypto_pay()

    with pytest.raises(ValueError, match="not found"):
        await escrow_service.release_escrow(session, crypto_pay, order_id=str(uuid.uuid4()))


@pytest.mark.asyncio
async def test_release_escrow_wrong_status(session: AsyncSession) -> None:
    """release_escrow raises ValueError for pending_funding orders."""
    order = await _create_order(session, OrderStatus.pending_funding)
    crypto_pay = _mock_crypto_pay()

    with pytest.raises(ValueError, match="requires status"):
        await escrow_service.release_escrow(session, crypto_pay, order_id=str(order.id))


@pytest.mark.asyncio
async def test_release_escrow_fiat_not_confirmed(session: AsyncSession) -> None:
    """release_escrow raises ValueError if fiat not confirmed and not force."""
    await _create_user(session, 503, "maker_503")
    await _create_user(session, 504, "taker_504")
    async with session.begin():
        order = Order(
            id=uuid.uuid4(),
            maker_id=503,
            taker_id=504,
            order_type=OrderType.sell_crypto,
            asset="USDT",
            amount=Decimal("100.0"),
            fiat_currency="USD",
            fiat_amount=Decimal("100.0"),
            payment_method="Sberbank",
            status=OrderStatus.escrow_held,
            spend_id=str(uuid.uuid4()),
            total_fee=Decimal("1.0"),
            fiat_confirmed=False,  # ← not confirmed
        )
        session.add(order)

    crypto_pay = _mock_crypto_pay()

    with pytest.raises(ValueError, match="Fiat payment not yet confirmed"):
        await escrow_service.release_escrow(session, crypto_pay, order_id=str(order.id))


# ── refund_escrow ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_refund_escrow_success(session: AsyncSession) -> None:
    """refund_escrow with force=True refunds to maker_id."""
    order = await _create_order(session, OrderStatus.escrow_held)
    crypto_pay = _mock_crypto_pay()

    result = await escrow_service.refund_escrow(
        session, crypto_pay, order_id=str(order.id), force=True
    )

    assert result["status"] == OrderStatus.cancelled
    call_kwargs = crypto_pay.transfer.call_args[1]
    assert call_kwargs["user_id"] == order.maker_id
    assert "refund-" in call_kwargs["spend_id"]


@pytest.mark.asyncio
async def test_refund_escrow_no_force_raises(session: AsyncSession) -> None:
    """refund_escrow without force=True raises ValueError immediately."""
    crypto_pay = _mock_crypto_pay()

    with pytest.raises(ValueError, match="requires force=True"):
        await escrow_service.refund_escrow(
            session, crypto_pay, order_id=str(uuid.uuid4()), force=False
        )


@pytest.mark.asyncio
async def test_refund_escrow_not_found(session: AsyncSession) -> None:
    """refund_escrow raises ValueError for unknown order."""
    crypto_pay = _mock_crypto_pay()

    with pytest.raises(ValueError, match="not found"):
        await escrow_service.refund_escrow(
            session, crypto_pay, order_id=str(uuid.uuid4()), force=True
        )


@pytest.mark.asyncio
async def test_refund_escrow_wrong_status(session: AsyncSession) -> None:
    """refund_escrow raises ValueError for pending_funding order."""
    order = await _create_order(session, OrderStatus.pending_funding)
    crypto_pay = _mock_crypto_pay()

    with pytest.raises(ValueError, match="invalid for status"):
        await escrow_service.refund_escrow(session, crypto_pay, order_id=str(order.id), force=True)


@pytest.mark.asyncio
async def test_refund_escrow_from_dispute(session: AsyncSession) -> None:
    """refund_escrow with force=True works from dispute status."""
    order = await _create_order(session, OrderStatus.dispute)
    crypto_pay = _mock_crypto_pay()

    result = await escrow_service.refund_escrow(
        session, crypto_pay, order_id=str(order.id), force=True
    )

    assert result["status"] == OrderStatus.cancelled
