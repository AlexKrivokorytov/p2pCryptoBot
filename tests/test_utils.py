"""Tests for datetime and message formatters."""

from __future__ import annotations

import uuid
from datetime import timedelta

from db.models.order import Order, OrderStatus
from utils import datetime_helpers, formatters


def test_utcnow() -> None:
    """Test utcnow returns aware datetime."""
    now = datetime_helpers.utcnow()
    assert now.tzinfo is not None


def test_is_order_expired() -> None:
    """Test order expiry logic."""
    order = Order(created_at=datetime_helpers.utcnow() - timedelta(seconds=100))

    assert datetime_helpers.is_order_expired(order, 50) is True
    assert datetime_helpers.is_order_expired(order, 150) is False


def test_seconds_until_expiry() -> None:
    """Test seconds until expiry calculation."""
    order = Order(created_at=datetime_helpers.utcnow() - timedelta(seconds=10))

    remaining = datetime_helpers.seconds_until_expiry(order, 30)
    assert 15 <= remaining <= 21

    expired = datetime_helpers.seconds_until_expiry(order, 5)
    assert expired == 0


def test_format_order_summary() -> None:
    """Test order summary formatting."""
    order = Order(
        id=uuid.uuid4(),
        order_type="sell_crypto",
        asset="USDT",
        amount=10.5,
        fiat_amount=1000.0,
        fiat_currency="RUB",
        payment_method="Sberbank",
        status=OrderStatus.pending_funding,
        total_fee=0.1,
    )
    summary = formatters.format_order_summary(order)
    assert "Order #" in summary
    assert "USDT" in summary
    assert "1000.00 RUB" in summary
    assert "pending_funding" in summary


def test_format_payment_instructions() -> None:
    """Test payment instructions formatting."""
    order = Order(id=uuid.uuid4(), asset="BTC", amount=0.001, payment_url="https://pay.link")
    instr = formatters.format_payment_instructions(order)
    assert "Pay via Crypto Pay" in instr
    assert "0.001 BTC" in instr
    assert "https://pay.link" in instr


def test_format_error() -> None:
    """Test error formatting."""
    err = formatters.format_error("something failed")
    assert "Error:" in err
    assert "something failed" in err


def test_format_dispute_raised() -> None:
    """Test dispute notification formatting."""
    order_id = str(uuid.uuid4())
    msg = formatters.format_dispute_raised(order_id, "no payment")
    assert "Dispute Raised" in msg
    assert "no payment" in msg
    assert order_id[:8] in msg
