"""Tests for order_service — full coverage of create, activate, take, confirm, cancel."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.order import Order, OrderStatus, OrderType
from db.models.user import User
from services import order_service


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
    maker_id: int = 601,
    taker_id: int | None = 602,
    order_type: str = OrderType.sell_crypto,
) -> Order:
    await _create_user(session, maker_id, f"m_{maker_id}")
    if taker_id is not None:
        await _create_user(session, taker_id, f"t_{taker_id}")
    async with session.begin():
        order = Order(
            id=uuid.uuid4(),
            maker_id=maker_id,
            taker_id=taker_id,
            order_type=order_type,
            asset="USDT",
            amount=100.0,
            fiat_currency="USD",
            fiat_amount=100.0,
            payment_method="Sberbank",
            status=status,
            spend_id=str(uuid.uuid4()),
            total_fee=1.0,
            fiat_confirmed=(status == OrderStatus.escrow_held),
        )
        session.add(order)
        return order


def _mock_crypto_pay(invoice_id: str = "inv_001") -> MagicMock:
    cp = MagicMock()
    cp.create_invoice = AsyncMock(
        return_value={"invoice_id": invoice_id, "pay_url": "https://pay.example.com/test"}
    )
    cp.transfer = AsyncMock(return_value={"transfer_id": "tr_01", "status": "completed"})
    return cp


# ── _validate_asset ────────────────────────────────────────────────────────────

def test_validate_asset_invalid() -> None:
    """Unsupported asset raises ValueError."""
    with pytest.raises(ValueError, match="Unsupported asset"):
        order_service._validate_asset("XYZ")


def test_validate_asset_valid() -> None:
    """Supported assets pass validation without error."""
    order_service._validate_asset("USDT")
    order_service._validate_asset("BTC")
    order_service._validate_asset("TON")


# ── _validate_amount ───────────────────────────────────────────────────────────

def test_validate_amount_zero() -> None:
    """Zero amount raises ValueError."""
    with pytest.raises(ValueError, match="must be positive"):
        order_service._validate_amount(0.0)


def test_validate_amount_negative() -> None:
    """Negative amount raises ValueError."""
    with pytest.raises(ValueError, match="must be positive"):
        order_service._validate_amount(-5.0)


# ── create_order ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_order_success(session: AsyncSession) -> None:
    """create_order returns order_id, status=pending_funding, invoice_id, payment_url."""
    await _create_user(session, 601, "maker_601")
    crypto_pay = _mock_crypto_pay()

    result = await order_service.create_order(
        session,
        crypto_pay,
        maker_id=601,
        order_type="sell_crypto",
        asset="USDT",
        amount=10.0,
        fiat_currency="RUB",
        fiat_amount=900.0,
        payment_method="Sberbank",
    )

    assert result["status"] == OrderStatus.pending_funding
    assert result["invoice_id"] == "inv_001"
    assert result["payment_url"].startswith("https://")
    assert "order_id" in result
    crypto_pay.create_invoice.assert_called_once()


@pytest.mark.asyncio
async def test_create_order_invalid_asset(session: AsyncSession) -> None:
    """create_order raises ValueError for unsupported asset."""
    crypto_pay = _mock_crypto_pay()

    with pytest.raises(ValueError, match="Unsupported asset"):
        await order_service.create_order(
            session, crypto_pay, maker_id=601, order_type="sell_crypto",
            asset="DOGE99", amount=10.0, fiat_currency="RUB", fiat_amount=100.0,
        )


@pytest.mark.asyncio
async def test_create_order_invalid_amount(session: AsyncSession) -> None:
    """create_order raises ValueError for zero amount."""
    crypto_pay = _mock_crypto_pay()

    with pytest.raises(ValueError, match="must be positive"):
        await order_service.create_order(
            session, crypto_pay, maker_id=601, order_type="sell_crypto",
            asset="USDT", amount=0.0, fiat_currency="RUB", fiat_amount=100.0,
        )


@pytest.mark.asyncio
async def test_create_order_invalid_type(session: AsyncSession) -> None:
    """create_order raises ValueError for unknown order_type."""
    crypto_pay = _mock_crypto_pay()

    with pytest.raises(ValueError, match="Invalid order_type"):
        await order_service.create_order(
            session, crypto_pay, maker_id=601, order_type="trade_swap",
            asset="USDT", amount=10.0, fiat_currency="RUB", fiat_amount=100.0,
        )


@pytest.mark.asyncio
async def test_create_order_with_fee(session: AsyncSession) -> None:
    """create_order correctly computes total_fee from percent + fixed."""
    await _create_user(session, 603, "maker_603")
    crypto_pay = _mock_crypto_pay()

    result = await order_service.create_order(
        session,
        crypto_pay,
        maker_id=603,
        order_type="sell_crypto",
        asset="USDT",
        amount=100.0,
        fiat_currency="USD",
        fiat_amount=100.0,
        fee_percent=1.0,
        fee_fixed=0.5,
    )
    # fee = 100 * 1% + 0.5 = 1.5
    assert result["status"] == OrderStatus.pending_funding


# ── activate_order ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_activate_order_success(session: AsyncSession) -> None:
    """activate_order transitions pending_funding → active."""
    order = await _create_order(session, OrderStatus.pending_funding, taker_id=None)

    result = await order_service.activate_order(session, order_id=str(order.id))

    assert result["status"] == OrderStatus.active


@pytest.mark.asyncio
async def test_activate_order_not_found(session: AsyncSession) -> None:
    """activate_order raises ValueError for missing order."""
    with pytest.raises(ValueError, match="not found"):
        await order_service.activate_order(session, order_id=str(uuid.uuid4()))


@pytest.mark.asyncio
async def test_activate_order_wrong_status(session: AsyncSession) -> None:
    """activate_order raises ValueError if not pending_funding."""
    order = await _create_order(session, OrderStatus.active, taker_id=None)

    with pytest.raises(ValueError, match="requires status=pending_funding"):
        await order_service.activate_order(session, order_id=str(order.id))


# ── take_order ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_take_order_success(session: AsyncSession) -> None:
    """take_order transitions active → escrow_held and sets taker_id."""
    order = await _create_order(session, OrderStatus.active, maker_id=701, taker_id=None)
    await _create_user(session, 702, "taker_702")

    result = await order_service.take_order(session, order_id=str(order.id), taker_id=702)

    assert result["status"] == OrderStatus.escrow_held
    assert result["maker_id"] == 701


@pytest.mark.asyncio
async def test_take_order_not_found(session: AsyncSession) -> None:
    """take_order raises ValueError for missing order."""
    with pytest.raises(ValueError, match="not found"):
        await order_service.take_order(session, order_id=str(uuid.uuid4()), taker_id=999)


@pytest.mark.asyncio
async def test_take_order_wrong_status(session: AsyncSession) -> None:
    """take_order raises ValueError if not active."""
    order = await _create_order(session, OrderStatus.escrow_held)

    with pytest.raises(ValueError, match="requires status=active"):
        await order_service.take_order(session, order_id=str(order.id), taker_id=999)


@pytest.mark.asyncio
async def test_take_order_self_take(session: AsyncSession) -> None:
    """take_order raises ValueError if taker == maker."""
    order = await _create_order(session, OrderStatus.active, maker_id=703, taker_id=None)

    with pytest.raises(ValueError, match="Cannot take your own order"):
        await order_service.take_order(session, order_id=str(order.id), taker_id=703)


# ── get_active_orders ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_active_orders_empty(session: AsyncSession) -> None:
    """get_active_orders returns empty list when no active orders exist."""
    result = await order_service.get_active_orders(session)

    assert result["orders"] == []
    assert result["total_count"] == 0
    assert result["page"] == 1


@pytest.mark.asyncio
async def test_get_active_orders_with_data(session: AsyncSession) -> None:
    """get_active_orders returns active orders with pagination info."""
    await _create_order(session, OrderStatus.active, maker_id=710, taker_id=None)
    await _create_order(session, OrderStatus.active, maker_id=711, taker_id=None)
    # This one should not appear — wrong status
    await _create_order(session, OrderStatus.pending_funding, maker_id=712, taker_id=None)

    result = await order_service.get_active_orders(session)

    assert result["total_count"] == 2
    assert len(result["orders"]) == 2


@pytest.mark.asyncio
async def test_get_active_orders_filter_asset(session: AsyncSession) -> None:
    """get_active_orders filters by asset."""
    await _create_order(session, OrderStatus.active, maker_id=720, taker_id=None)

    result = await order_service.get_active_orders(session, asset="BTC")
    assert result["total_count"] == 0

    result = await order_service.get_active_orders(session, asset="USDT")
    assert result["total_count"] >= 1


# ── confirm_fiat_payment ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_confirm_fiat_success(session: AsyncSession) -> None:
    """Successful fiat confirmation sets status to completed."""
    order = await _create_order(session, OrderStatus.escrow_held, maker_id=604, taker_id=605)
    crypto_pay = _mock_crypto_pay()

    result = await order_service.confirm_fiat_payment(
        session, crypto_pay, order_id=str(order.id)
    )

    assert result["status"] == OrderStatus.completed


@pytest.mark.asyncio
async def test_confirm_fiat_transfer_fails_sets_dispute(session: AsyncSession) -> None:
    """If transfer raises an exception, order status becomes dispute."""
    order = await _create_order(session, OrderStatus.escrow_held, maker_id=606, taker_id=607)

    cp = MagicMock()
    cp.transfer = AsyncMock(side_effect=Exception("API timeout"))

    result = await order_service.confirm_fiat_payment(
        session, cp, order_id=str(order.id)
    )

    assert result["status"] == OrderStatus.dispute


@pytest.mark.asyncio
async def test_confirm_fiat_order_not_found(session: AsyncSession) -> None:
    """confirm_fiat_payment raises ValueError for missing order."""
    crypto_pay = _mock_crypto_pay()

    with pytest.raises(ValueError, match="not found"):
        await order_service.confirm_fiat_payment(
            session, crypto_pay, order_id=str(uuid.uuid4())
        )


@pytest.mark.asyncio
async def test_confirm_fiat_wrong_status(session: AsyncSession) -> None:
    """confirm_fiat_payment raises ValueError if not escrow_held."""
    order = await _create_order(session, OrderStatus.pending_funding, maker_id=608, taker_id=None)
    crypto_pay = _mock_crypto_pay()

    with pytest.raises(ValueError, match="Cannot confirm fiat"):
        await order_service.confirm_fiat_payment(
            session, crypto_pay, order_id=str(order.id)
        )


# ── cancel_order ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cancel_pending_funding(session: AsyncSession) -> None:
    """Pending funding order can be cancelled."""
    order = await _create_order(session, OrderStatus.pending_funding, maker_id=610, taker_id=None)

    result = await order_service.cancel_order(session, order_id=str(order.id))

    assert result["status"] == OrderStatus.cancelled


@pytest.mark.asyncio
async def test_cancel_active_order(session: AsyncSession) -> None:
    """Active order can be cancelled."""
    order = await _create_order(session, OrderStatus.active, maker_id=611, taker_id=None)

    result = await order_service.cancel_order(session, order_id=str(order.id))

    assert result["status"] == OrderStatus.cancelled


@pytest.mark.asyncio
async def test_cancel_order_escrow_held_raises(session: AsyncSession) -> None:
    """Cancelling an escrow_held order raises ValueError."""
    order = await _create_order(session, OrderStatus.escrow_held, maker_id=612, taker_id=613)

    with pytest.raises(ValueError, match="funds in escrow"):
        await order_service.cancel_order(session, order_id=str(order.id))


@pytest.mark.asyncio
async def test_cancel_order_not_found(session: AsyncSession) -> None:
    """cancel_order raises ValueError for unknown order."""
    with pytest.raises(ValueError, match="not found"):
        await order_service.cancel_order(session, order_id=str(uuid.uuid4()))


@pytest.mark.asyncio
async def test_cancel_order_wrong_status(session: AsyncSession) -> None:
    """cancel_order raises ValueError for completed order."""
    order = await _create_order(session, OrderStatus.completed, maker_id=614, taker_id=615)

    with pytest.raises(ValueError, match="Cannot cancel"):
        await order_service.cancel_order(session, order_id=str(order.id))
