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


# ── find_user_by_query ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_find_user_by_query_username(mocker: MagicMock) -> None:
    from services.admin_user_service import find_user_by_query

    session = MagicMock()
    session.execute = mocker.AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = _make_user()
    session.execute.return_value = mock_result

    user = await find_user_by_query(session, "@alice")
    assert user is not None
    assert user.username == "alice"


@pytest.mark.asyncio
async def test_find_user_by_query_id(mocker: MagicMock) -> None:
    from services.admin_user_service import find_user_by_query

    session = MagicMock()
    session.execute = mocker.AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = _make_user()
    session.execute.return_value = mock_result

    user = await find_user_by_query(session, "123456")
    assert user is not None
    assert user.telegram_id == 123456


@pytest.mark.asyncio
async def test_find_user_by_query_username_no_at(mocker: MagicMock) -> None:
    from services.admin_user_service import find_user_by_query

    session = MagicMock()
    session.execute = mocker.AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = _make_user()
    session.execute.return_value = mock_result

    user = await find_user_by_query(session, "alice")
    assert user is not None


# ── toggle_user_verification ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_toggle_user_verification(mocker: MagicMock) -> None:
    from services.admin_user_service import toggle_user_verification

    session = MagicMock()
    session.execute = mocker.AsyncMock()
    session.commit = mocker.AsyncMock()
    mock_result = MagicMock()
    user_mock = _make_user(is_verified=False)
    mock_result.scalar_one_or_none.return_value = user_mock
    session.execute.return_value = mock_result

    log_admin_action_mock = mocker.patch(
        "services.admin_user_service.log_admin_action", new_callable=mocker.AsyncMock
    )

    await toggle_user_verification(session, 111, 222, True)

    assert user_mock.is_verified is True
    log_admin_action_mock.assert_called_once()
    session.commit.assert_called_once()
