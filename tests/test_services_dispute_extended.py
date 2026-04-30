"""Tests for dispute_service — full coverage including ai_mediator_suggest."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.order import Order, OrderStatus, OrderType
from db.models.user import User
from services import dispute_service


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
    maker_id: int = 701,
    taker_id: int = 702,
) -> Order:
    await _create_user(session, maker_id, f"m_{maker_id}")
    await _create_user(session, taker_id, f"t_{taker_id}")
    async with session.begin():
        order = Order(
            id=uuid.uuid4(),
            maker_id=maker_id,
            taker_id=taker_id,
            order_type=OrderType.sell_crypto,
            asset="TON",
            amount=50.0,
            fiat_currency="USD",
            fiat_amount=100.0,
            payment_method="Sberbank",
            status=status,
            spend_id=str(uuid.uuid4()),
            total_fee=0.5,
            fiat_confirmed=False,
        )
        session.add(order)
        return order


def _mock_crypto_pay() -> MagicMock:
    cp = MagicMock()
    cp.transfer = AsyncMock(return_value={"transfer_id": "tr_d1", "status": "completed"})
    return cp


# ── raise_dispute ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_raise_dispute_from_active(session: AsyncSession) -> None:
    """Dispute can be raised from active status."""
    order = await _create_order(session, OrderStatus.active, 703, 704)

    result = await dispute_service.raise_dispute(
        session, order_id=str(order.id), reason="No payment received", raised_by=703
    )

    assert result["status"] == OrderStatus.dispute


@pytest.mark.asyncio
async def test_raise_dispute_order_not_found(session: AsyncSession) -> None:
    """raise_dispute raises ValueError for unknown order."""
    with pytest.raises(ValueError, match="not found"):
        await dispute_service.raise_dispute(
            session, order_id=str(uuid.uuid4()), reason="test", raised_by=999
        )


@pytest.mark.asyncio
async def test_raise_dispute_wrong_status(session: AsyncSession) -> None:
    """raise_dispute raises ValueError for completed order."""
    order = await _create_order(session, OrderStatus.completed, 705, 706)

    with pytest.raises(ValueError, match="Cannot raise dispute"):
        await dispute_service.raise_dispute(
            session, order_id=str(order.id), reason="late", raised_by=705
        )


# ── resolve_dispute ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_resolve_dispute_cancel_decision(session: AsyncSession) -> None:
    """Decision 'cancel' triggers refund_escrow and returns cancelled status."""
    order = await _create_order(session, OrderStatus.dispute, 707, 708)
    crypto_pay = _mock_crypto_pay()

    result = await dispute_service.resolve_dispute(
        session, crypto_pay, order_id=str(order.id), decision="cancel", moderator_id=999
    )

    assert result["status"] == OrderStatus.cancelled
    assert result["decision"] == "cancel"


@pytest.mark.asyncio
async def test_resolve_dispute_order_not_found(session: AsyncSession) -> None:
    """resolve_dispute raises ValueError for unknown order."""
    crypto_pay = _mock_crypto_pay()

    with pytest.raises(ValueError, match="not found"):
        await dispute_service.resolve_dispute(
            session, crypto_pay, order_id=str(uuid.uuid4()),
            decision="taker_wins", moderator_id=999
        )


@pytest.mark.asyncio
async def test_resolve_dispute_wrong_status(session: AsyncSession) -> None:
    """resolve_dispute raises ValueError if order is not in dispute."""
    order = await _create_order(session, OrderStatus.escrow_held, 709, 710)
    crypto_pay = _mock_crypto_pay()

    with pytest.raises(ValueError, match="requires status=dispute"):
        await dispute_service.resolve_dispute(
            session, crypto_pay, order_id=str(order.id),
            decision="taker_wins", moderator_id=999
        )


# ── ai_mediator_suggest ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ai_mediator_no_key() -> None:
    """Without GEMINI_API_KEY, ai_mediator_suggest returns no suggestion."""
    with patch.dict("os.environ", {}, clear=False):
        # Ensure key is absent
        import os
        os.environ.pop("GEMINI_API_KEY", None)

        result = await dispute_service.ai_mediator_suggest(
            order_id=str(uuid.uuid4()), chat_history=None
        )

    assert result["suggestion"] is None
    assert result["confidence"] == 0.0
    assert "not configured" in result["reasoning"]


@pytest.mark.asyncio
async def test_ai_mediator_with_key_stub() -> None:
    """With GEMINI_API_KEY set, stub returns neutral suggestion."""
    with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key-abc123"}):
        result = await dispute_service.ai_mediator_suggest(
            order_id=str(uuid.uuid4()),
            chat_history=[{"role": "maker", "text": "I paid!"}, {"role": "taker", "text": "I got nothing."}],
        )

    assert result["suggestion"] == "neutral"
    assert result["confidence"] == 0.0


@pytest.mark.asyncio
async def test_ai_mediator_with_empty_chat_history() -> None:
    """ai_mediator_suggest handles None chat_history without error."""
    with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key-abc123"}):
        result = await dispute_service.ai_mediator_suggest(
            order_id=str(uuid.uuid4()), chat_history=None
        )

    assert "suggestion" in result
    assert "reasoning" in result
