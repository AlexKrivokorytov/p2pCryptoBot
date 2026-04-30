"""Tests for dispute service: raising and resolving disputes."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.order import Order, OrderStatus, OrderType
from db.models.user import User
from services import dispute_service


async def _create_order(
    session: AsyncSession, status: OrderStatus = OrderStatus.escrow_held
) -> Order:
    maker = User(telegram_id=201, username="maker")
    taker = User(telegram_id=202, username="taker")

    order = Order(
        maker_id=201,
        taker_id=202,
        order_type=OrderType.sell_crypto,
        asset="TON",
        amount=50.0,
        fiat_currency="USD",
        fiat_amount=100.0,
        payment_method="Sberbank",
        status=status,
        spend_id=str(uuid.uuid4()),
    )
    async with session.begin():
        session.add_all([maker, taker])
        session.add(order)
    return order


def _mock_crypto_pay() -> MagicMock:
    cp = MagicMock()
    cp.transfer = AsyncMock(return_value={"transfer_id": "tr_2", "status": "completed"})
    return cp


@pytest.mark.asyncio
async def test_raise_dispute_success(session: AsyncSession) -> None:
    """Dispute can be raised on an escrow_held order."""
    order = await _create_order(session, status=OrderStatus.escrow_held)

    result = await dispute_service.raise_dispute(
        session, order_id=str(order.id), reason="Taker didn't pay fiat", raised_by=201
    )

    assert result["status"] == OrderStatus.dispute


@pytest.mark.asyncio
async def test_raise_dispute_invalid_status(session: AsyncSession) -> None:
    """Dispute cannot be raised if order is already completed."""
    order = await _create_order(session, status=OrderStatus.completed)

    with pytest.raises(ValueError, match="Cannot raise dispute"):
        await dispute_service.raise_dispute(
            session, order_id=str(order.id), reason="Late dispute", raised_by=201
        )


@pytest.mark.asyncio
async def test_resolve_dispute_taker_wins(session: AsyncSession) -> None:
    """If taker wins, funds go to taker and status becomes completed."""
    order = await _create_order(session, status=OrderStatus.dispute)
    crypto_pay = _mock_crypto_pay()

    result = await dispute_service.resolve_dispute(
        session, crypto_pay, order_id=str(order.id), decision="taker_wins", moderator_id=999
    )

    assert result["status"] == OrderStatus.completed
    args, kwargs = crypto_pay.transfer.call_args
    assert kwargs["user_id"] == 202  # taker gets crypto (sell_crypto order)


@pytest.mark.asyncio
async def test_resolve_dispute_maker_wins(session: AsyncSession) -> None:
    """If maker wins, funds are refunded to maker and status becomes cancelled."""
    order = await _create_order(session, status=OrderStatus.dispute)
    crypto_pay = _mock_crypto_pay()

    result = await dispute_service.resolve_dispute(
        session, crypto_pay, order_id=str(order.id), decision="maker_wins", moderator_id=999
    )

    assert result["status"] == OrderStatus.cancelled
    args, kwargs = crypto_pay.transfer.call_args
    assert kwargs["user_id"] == 201  # maker gets refund


@pytest.mark.asyncio
async def test_resolve_dispute_invalid_decision(session: AsyncSession) -> None:
    """Invalid decision should raise ValueError."""
    order = await _create_order(session, status=OrderStatus.dispute)
    crypto_pay = _mock_crypto_pay()

    with pytest.raises(ValueError, match="Invalid decision"):
        await dispute_service.resolve_dispute(
            session, crypto_pay, order_id=str(order.id), decision="draw", moderator_id=999
        )
