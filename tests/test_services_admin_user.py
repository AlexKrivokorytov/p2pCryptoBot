"""Unit tests for services/admin_user_service.py — find_user_by_query and format_user_info."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from services.admin_user_service import format_user_info

pytestmark = pytest.mark.unit


def _make_user(
    telegram_id: int = 123456,
    username: str | None = "alice",
    first_name: str = "Alice",
    is_verified: bool = True,
    total_trades: int = 50,
    successful_trades: int = 48,
) -> MagicMock:
    """Build a mocked User for admin display tests."""
    user = MagicMock()
    user.telegram_id = telegram_id
    user.username = username
    user.first_name = first_name
    user.is_verified = is_verified
    user.total_trades = total_trades
    user.successful_trades = successful_trades
    return user


# ── format_user_info ───────────────────────────────────────────────────────────


def test_format_user_info_verified_user() -> None:
    """Shows ✅ Verified status for verified users."""
    user = _make_user(is_verified=True)
    result = format_user_info(user)
    assert "✅ Verified" in result
    assert "123456" in result
    assert "@alice" in result
    assert "Alice" in result


def test_format_user_info_unverified_user() -> None:
    """Shows ❌ Unverified status for unverified users."""
    user = _make_user(is_verified=False)
    result = format_user_info(user)
    assert "❌ Unverified" in result


def test_format_user_info_no_username() -> None:
    """Handles None username gracefully with em-dash."""
    user = _make_user(username=None)
    result = format_user_info(user)
    assert "—" in result


def test_format_user_info_no_first_name() -> None:
    """Handles None first_name gracefully with em-dash."""
    user = _make_user(first_name=None)
    result = format_user_info(user)
    assert "—" in result


def test_format_user_info_includes_trade_stats() -> None:
    """Shows total_trades and successful_trades."""
    user = _make_user(total_trades=100, successful_trades=95)
    result = format_user_info(user)
    assert "100" in result
    assert "95" in result


def test_format_user_info_zero_trades() -> None:
    """New user with zero trades displays correctly."""
    user = _make_user(total_trades=0, successful_trades=0)
    result = format_user_info(user)
    assert "Total Trades" in result
    assert "0" in result


def test_format_user_info_contains_html_tags() -> None:
    """Output includes HTML formatting for Telegram."""
    user = _make_user()
    result = format_user_info(user)
    assert "<b>" in result
    assert "<code>" in result
