"""Date/time helpers — UTC-aware utilities for order expiry checks."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from db.models.order import Order


def utcnow() -> datetime:
    """Return current UTC time as a timezone-aware datetime."""
    return datetime.now(UTC)


def is_order_expired(order: Order, timeout_sec: int) -> bool:
    """Check whether an order has exceeded its allowed lifetime.

    Args:
        order: The Order ORM instance to check.
        timeout_sec: Maximum age in seconds before the order is considered expired.

    Returns:
        ``True`` if the order is older than *timeout_sec*, ``False`` otherwise.
    """
    created = order.created_at
    # Ensure timezone-aware comparison
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    deadline = created + timedelta(seconds=timeout_sec)
    return utcnow() > deadline


def seconds_until_expiry(order: Order, timeout_sec: int) -> int:
    """Return seconds remaining until the order expires (0 if already expired).

    Args:
        order: The Order ORM instance.
        timeout_sec: Order lifetime in seconds.

    Returns:
        Non-negative integer seconds remaining.
    """
    created = order.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    deadline = created + timedelta(seconds=timeout_sec)
    remaining = (deadline - utcnow()).total_seconds()
    return max(0, int(remaining))
