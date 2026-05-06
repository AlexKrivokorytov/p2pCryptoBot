"""Tests for dispute_service — full coverage including ai_mediator_suggest."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.order import Order, OrderStatus, OrderType
from db.models.user import User
from services import dispute_service

pytestmark = pytest.mark.unit

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
            session, crypto_pay, order_id=str(uuid.uuid4()), decision="taker_wins", moderator_id=999
        )


@pytest.mark.asyncio
async def test_resolve_dispute_wrong_status(session: AsyncSession) -> None:
    """resolve_dispute raises ValueError if order is not in dispute."""
    order = await _create_order(session, OrderStatus.escrow_held, 709, 710)
    crypto_pay = _mock_crypto_pay()

    with pytest.raises(ValueError, match="requires status=dispute"):
        await dispute_service.resolve_dispute(
            session, crypto_pay, order_id=str(order.id), decision="taker_wins", moderator_id=999
        )


# ── ai_mediator_suggest ────────────────────────────────────────────────────────


class MockResponse:
    def __init__(self, text: str):
        self.text = text


@pytest.mark.asyncio
async def test_ai_mediator_no_key() -> None:
    """Returns neutral suggestion when GEMINI_API_KEY is missing."""
    with patch.dict("os.environ", {"GEMINI_API_KEY": ""}):
        result = await dispute_service.ai_mediator_suggest("order-123")
        assert result["suggestion"] is None
        assert "not configured" in result["reasoning"]
        assert result["confidence"] == 0.0


@pytest.mark.asyncio
async def test_ai_mediator_gemini_returns_taker_wins() -> None:
    """Mocks Gemini returning taker_wins and verifies parsing."""
    json_data = '{"suggestion": "taker_wins", "reasoning": "Taker paid.", "confidence": 0.9}'

    with (
        patch.dict("os.environ", {"GEMINI_API_KEY": "fake-key"}),
        patch("services.dispute_service.asyncio.to_thread") as mock_thread,
    ):
        mock_thread.return_value = MockResponse(json_data)

        result = await dispute_service.ai_mediator_suggest("order-123")
        assert result["suggestion"] == "taker_wins"
        assert result["reasoning"] == "Taker paid."
        assert result["confidence"] == 0.9


@pytest.mark.asyncio
async def test_ai_mediator_gemini_returns_maker_wins() -> None:
    """Mocks Gemini returning maker_wins and verifies parsing."""
    json_data = (
        '{"suggestion": "maker_wins", "reasoning": "Maker did not receive.", "confidence": 0.85}'
    )

    with (
        patch.dict("os.environ", {"GEMINI_API_KEY": "fake-key"}),
        patch("services.dispute_service.asyncio.to_thread") as mock_thread,
    ):
        mock_thread.return_value = MockResponse(json_data)

        result = await dispute_service.ai_mediator_suggest("order-123")
        assert result["suggestion"] == "maker_wins"
        assert result["confidence"] == 0.85


@pytest.mark.asyncio
async def test_ai_mediator_gemini_error_returns_neutral() -> None:
    """Gemini raises exception, returns neutral."""
    with (
        patch.dict("os.environ", {"GEMINI_API_KEY": "fake-key"}),
        patch("services.dispute_service.asyncio.to_thread") as mock_thread,
    ):
        mock_thread.side_effect = Exception("API Error")

        result = await dispute_service.ai_mediator_suggest("order-123")
        assert result["suggestion"] == "neutral"
        assert "API Error" in result["reasoning"]
        assert result["confidence"] == 0.0


@pytest.mark.asyncio
async def test_ai_mediator_gemini_invalid_json_returns_neutral() -> None:
    """Gemini returns bad JSON, returns neutral."""
    with (
        patch.dict("os.environ", {"GEMINI_API_KEY": "fake-key"}),
        patch("services.dispute_service.asyncio.to_thread") as mock_thread,
    ):
        mock_thread.return_value = MockResponse("Not JSON")

        result = await dispute_service.ai_mediator_suggest("order-123")
        assert result["suggestion"] == "neutral"
        assert result["confidence"] == 0.0


@pytest.mark.asyncio
async def test_ai_mediator_gemini_markdown_fences_stripped() -> None:
    """Response wrapped in markdown fences is parsed correctly."""
    json_data = '```json\n{"suggestion": "taker_wins", "reasoning": "Test", "confidence": 1.0}\n```'

    with (
        patch.dict("os.environ", {"GEMINI_API_KEY": "fake-key"}),
        patch("services.dispute_service.asyncio.to_thread") as mock_thread,
    ):
        mock_thread.return_value = MockResponse(json_data)

        result = await dispute_service.ai_mediator_suggest("order-123")
        assert result["suggestion"] == "taker_wins"
        assert result["confidence"] == 1.0


@pytest.mark.asyncio
async def test_ai_mediator_invalid_suggestion_value_normalized() -> None:
    """Unknown suggestion value becomes neutral."""
    json_data = '{"suggestion": "unknown_value", "reasoning": "??", "confidence": 0.5}'

    with (
        patch.dict("os.environ", {"GEMINI_API_KEY": "fake-key"}),
        patch("services.dispute_service.asyncio.to_thread") as mock_thread,
    ):
        mock_thread.return_value = MockResponse(json_data)

        result = await dispute_service.ai_mediator_suggest("order-123")
        assert result["suggestion"] == "neutral"
