"""Tests for admin handlers — /admin, /stats, /disputes, dispute resolution."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from bot.handlers import admin as admin_handlers
from bot.states import ArbitrationFSM

# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def mock_admin_ids() -> None:
    """Patch settings.ADMIN_IDS so that user_id=999 is admin, 123 is not."""
    with patch.object(admin_handlers, "_is_admin", side_effect=lambda uid: uid == 999):
        yield


# ── /arbitrate command ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cmd_arbitrate_not_admin() -> None:
    """Non-admin should be rejected."""
    message = AsyncMock()
    message.from_user.id = 123
    state = AsyncMock(spec=FSMContext)

    await admin_handlers.cmd_arbitrate(message, state)

    state.set_state.assert_not_called()
    message.answer.assert_called_once_with("⛔ Admins only.")


@pytest.mark.asyncio
async def test_cmd_arbitrate_admin() -> None:
    """Admin should be prompted for order ID."""
    message = AsyncMock()
    message.from_user.id = 999
    state = AsyncMock(spec=FSMContext)

    await admin_handlers.cmd_arbitrate(message, state)

    state.set_state.assert_called_once_with(ArbitrationFSM.enter_order_id)
    message.answer.assert_called_once()
    assert "Order ID" in message.answer.call_args[0][0]


# ── /admin command ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cmd_admin_not_admin() -> None:
    """Non-admin receives rejection for /admin."""
    message = AsyncMock()
    message.from_user.id = 123

    await admin_handlers.cmd_admin(message)

    message.answer.assert_called_once_with("⛔ Admins only.")


@pytest.mark.asyncio
async def test_cmd_admin_shows_dashboard() -> None:
    """Admin receives dashboard menu."""
    message = AsyncMock()
    message.from_user.id = 999

    await admin_handlers.cmd_admin(message)

    message.answer.assert_called_once()
    text = message.answer.call_args[0][0]
    assert "Admin Dashboard" in text


# ── /stats command ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@patch("bot.handlers.admin.admin_service.get_platform_stats", new_callable=AsyncMock)
@patch("bot.handlers.admin.admin_service.format_stats_message", return_value="📊 Stats")
async def test_cmd_stats_admin(
    mock_format: MagicMock,
    mock_stats: AsyncMock,
    session: AsyncSession,
) -> None:
    """Admin /stats shows formatted stats."""
    mock_stats.return_value = MagicMock()
    message = AsyncMock()
    message.from_user.id = 999

    await admin_handlers.cmd_stats(message, session)

    mock_stats.assert_called_once()
    message.answer.assert_called_once()
    assert "Stats" in message.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_cmd_stats_not_admin(session: AsyncSession) -> None:
    """Non-admin is rejected from /stats."""
    message = AsyncMock()
    message.from_user.id = 123

    await admin_handlers.cmd_stats(message, session)

    message.answer.assert_called_once_with("⛔ Admins only.")


# ── /disputes command ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
@patch("bot.handlers.admin.admin_service.get_dispute_queue", new_callable=AsyncMock)
async def test_cmd_disputes_no_disputes(mock_queue: AsyncMock, session: AsyncSession) -> None:
    """Admin /disputes shows empty state message."""
    mock_queue.return_value = []
    message = AsyncMock()
    message.from_user.id = 999

    await admin_handlers.cmd_disputes(message, session)

    message.answer.assert_called_once()
    text = message.answer.call_args[0][0]
    assert "Dispute Queue" in text


@pytest.mark.asyncio
async def test_cmd_disputes_not_admin(session: AsyncSession) -> None:
    """Non-admin is rejected from /disputes."""
    message = AsyncMock()
    message.from_user.id = 123

    await admin_handlers.cmd_disputes(message, session)

    message.answer.assert_called_once_with("⛔ Admins only.")


# ── Dispute resolution callback ───────────────────────────────────────────────


@pytest.mark.asyncio
@patch("bot.handlers.admin.dispute_service.resolve_dispute", new_callable=AsyncMock)
async def test_cb_dispute_resolve_not_admin(mock_resolve: AsyncMock, session: AsyncSession) -> None:
    """Non-admin resolving via callback is rejected."""
    callback = AsyncMock()
    callback.from_user.id = 123
    callback.data = "dispute:resolve:12345678:taker_wins"
    state = AsyncMock(spec=FSMContext)
    crypto_pay = AsyncMock()

    await admin_handlers.cb_dispute_resolve(callback, state, session, crypto_pay)

    callback.answer.assert_called_once_with("⛔ Admins only.", show_alert=True)
    mock_resolve.assert_not_called()


@pytest.mark.asyncio
@patch("bot.handlers.admin.dispute_service.resolve_dispute", new_callable=AsyncMock)
async def test_cb_dispute_resolve_success(mock_resolve: AsyncMock, session: AsyncSession) -> None:
    """Admin successfully resolves dispute."""
    mock_resolve.return_value = {"status": "completed"}

    callback = AsyncMock()
    callback.from_user.id = 999
    callback.data = "dispute:resolve:5a1fc458:taker_wins"
    state = AsyncMock(spec=FSMContext)
    crypto_pay = AsyncMock()

    await admin_handlers.cb_dispute_resolve(callback, state, session, crypto_pay)

    mock_resolve.assert_called_once_with(
        session, crypto_pay, order_id="5a1fc458", decision="taker_wins", moderator_id=999
    )
    callback.message.edit_text.assert_called_once()
    assert "Dispute resolved" in callback.message.edit_text.call_args[0][0]
    callback.answer.assert_called_once()


@pytest.mark.asyncio
@patch("bot.handlers.admin.dispute_service.resolve_dispute", new_callable=AsyncMock)
async def test_cb_dispute_resolve_error(mock_resolve: AsyncMock, session: AsyncSession) -> None:
    """Admin dispute resolution handles service errors gracefully."""
    mock_resolve.side_effect = ValueError("Order not found")

    callback = AsyncMock()
    callback.from_user.id = 999
    callback.data = "dispute:resolve:5a1fc458:taker_wins"
    state = AsyncMock(spec=FSMContext)
    crypto_pay = AsyncMock()

    await admin_handlers.cb_dispute_resolve(callback, state, session, crypto_pay)

    callback.message.edit_text.assert_called_once()
    assert "Order not found" in callback.message.edit_text.call_args[0][0]


# ── msg_arb_order_id ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_msg_arb_order_id_invalid() -> None:
    """Invalid (short) order ID is rejected."""
    message = AsyncMock()
    message.text = "short"
    state = AsyncMock(spec=FSMContext)

    await admin_handlers.msg_arb_order_id(message, state)

    state.update_data.assert_not_called()
    message.answer.assert_called_once()
    assert "Invalid order ID" in message.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_msg_arb_order_id_valid() -> None:
    """Valid order ID proceeds to decision stage."""
    message = AsyncMock()
    message.text = "5a1fc458-83ae-40bd-ac61-30c578b45827"
    state = AsyncMock(spec=FSMContext)

    await admin_handlers.msg_arb_order_id(message, state)

    state.update_data.assert_called_once_with(order_id="5a1fc458-83ae-40bd-ac61-30c578b45827")
    state.set_state.assert_called_once_with(ArbitrationFSM.choose_decision)
    message.answer.assert_called_once()
    assert "Choose decision" in message.answer.call_args[0][0]
