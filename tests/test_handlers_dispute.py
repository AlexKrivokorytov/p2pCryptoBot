"""Tests for dispute handlers."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from bot.handlers import dispute as dispute_handlers
from bot.states import DisputeFSM


@pytest.mark.asyncio
async def test_cb_dispute_raise() -> None:
    """Test start dispute flow."""
    callback = AsyncMock()
    callback.data = "dispute:raise:12345"
    state = AsyncMock(spec=FSMContext)

    await dispute_handlers.cb_dispute_raise(callback, state)

    state.set_state.assert_called_once_with(DisputeFSM.enter_reason)
    state.update_data.assert_called_once_with(order_id="12345")
    callback.message.answer.assert_called_once()
    assert "Raise a Dispute" in callback.message.answer.call_args[0][0]
    callback.answer.assert_called_once()


@pytest.mark.asyncio
async def test_msg_dispute_reason_empty() -> None:
    """Empty reason should be rejected."""
    message = AsyncMock()
    message.text = "   "
    state = AsyncMock(spec=FSMContext)

    await dispute_handlers.msg_dispute_reason(message, state)

    state.update_data.assert_not_called()
    message.answer.assert_called_once()
    assert "Reason cannot be empty" in message.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_msg_dispute_reason_valid() -> None:
    """Valid reason proceeds to confirmation."""
    message = AsyncMock()
    message.text = "Seller did not reply"
    state = AsyncMock(spec=FSMContext)

    await dispute_handlers.msg_dispute_reason(message, state)

    state.update_data.assert_called_once_with(reason="Seller did not reply")
    state.set_state.assert_called_once_with(DisputeFSM.confirm_dispute)
    message.answer.assert_called_once()
    assert "Seller did not reply" in message.answer.call_args[0][0]


@pytest.mark.asyncio
@patch("bot.handlers.dispute.dispute_service.raise_dispute", new_callable=AsyncMock)
async def test_cb_dispute_confirmed_success(mock_raise: AsyncMock, session: AsyncSession) -> None:
    """Confirming dispute calls the service successfully."""
    callback = AsyncMock()
    callback.from_user.id = 123
    state = AsyncMock(spec=FSMContext)
    state.get_data.return_value = {
        "order_id": "5a1fc458-0000-0000-0000-000000000000",
        "reason": "reason here",
    }

    await dispute_handlers.cb_dispute_confirmed(callback, state, session, bot=AsyncMock())

    mock_raise.assert_called_once_with(
        session,
        order_id="5a1fc458-0000-0000-0000-000000000000",
        reason="reason here",
        raised_by=123,
    )
    state.clear.assert_called_once()
    callback.message.edit_text.assert_called_once()
    callback.answer.assert_called_once()


@pytest.mark.asyncio
@patch("bot.handlers.dispute.dispute_service.raise_dispute", new_callable=AsyncMock)
async def test_cb_dispute_confirmed_error(mock_raise: AsyncMock, session: AsyncSession) -> None:
    """Errors during dispute creation are shown to the user."""
    mock_raise.side_effect = ValueError("Order not found")

    callback = AsyncMock()
    callback.from_user.id = 123
    state = AsyncMock(spec=FSMContext)
    state.get_data.return_value = {
        "order_id": "5a1fc458-0000-0000-0000-000000000000",
        "reason": "reason here",
    }

    await dispute_handlers.cb_dispute_confirmed(callback, state, session, bot=AsyncMock())

    callback.message.edit_text.assert_called_once()
    assert "Order not found" in callback.message.edit_text.call_args[0][0]
    callback.answer.assert_called_once()


@pytest.mark.asyncio
async def test_cb_dispute_abort() -> None:
    """Aborting dispute clears state."""
    callback = AsyncMock()
    state = AsyncMock(spec=FSMContext)

    await dispute_handlers.cb_dispute_abort(callback, state)

    state.clear.assert_called_once()
    callback.message.edit_text.assert_called_once()
    assert "Dispute cancelled" in callback.message.edit_text.call_args[0][0]
    callback.answer.assert_called_once()
