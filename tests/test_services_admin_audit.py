"""Tests for admin audit service functions — unit coverage."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from services.admin_audit_service import format_log_entry, format_logs_message

pytestmark = pytest.mark.unit


def _make_log(
    action: str = "inject_balance",
    admin_id: int = 123,
    target_id: int = 456,
    details: dict | None = None,
    ts: datetime | None = None,
) -> MagicMock:
    """Build a mocked AdminAuditLog."""
    log = MagicMock()
    log.action = action
    log.admin_id = admin_id
    log.target_id = target_id
    log.details = details or {"amount": "100", "asset": "USDT"}
    log.created_at = ts or datetime(2025, 1, 15, 10, 30, 0)
    return log


# ── format_log_entry ──────────────────────────────────────────────────────────


def test_format_log_entry_inject_balance() -> None:
    """format_log_entry uses 💰 icon for inject_balance."""
    log = _make_log(action="inject_balance")
    result = format_log_entry(log)
    assert "💰" in result
    assert "inject_balance" in result
    assert "123" in result  # admin_id
    assert "456" in result  # target_id


def test_format_log_entry_activate_license() -> None:
    """format_log_entry uses 💎 icon for activate_license_bypass."""
    log = _make_log(action="activate_license_bypass")
    result = format_log_entry(log)
    assert "💎" in result
    assert "activate_license_bypass" in result


def test_format_log_entry_force_order_status() -> None:
    """format_log_entry uses ⚙️ icon for force_order_status."""
    log = _make_log(action="force_order_status")
    result = format_log_entry(log)
    assert "⚙️" in result


def test_format_log_entry_unknown_action_uses_default_icon() -> None:
    """format_log_entry uses 📝 icon for unknown actions."""
    log = _make_log(action="some_custom_action")
    result = format_log_entry(log)
    assert "📝" in result


def test_format_log_entry_no_target_id() -> None:
    """format_log_entry handles None target_id gracefully."""
    log = _make_log(target_id=None)
    result = format_log_entry(log)
    assert "—" in result  # em-dash for missing target


def test_format_log_entry_no_created_at() -> None:
    """format_log_entry handles missing created_at."""
    log = _make_log(ts=None)
    log.created_at = None
    result = format_log_entry(log)
    assert "N/A" in result


def test_format_log_entry_no_details() -> None:
    """format_log_entry handles empty details dict."""
    log = _make_log(details={})
    result = format_log_entry(log)
    # Should not error; details line is empty
    assert "inject_balance" in result


def test_format_log_entry_with_multiple_details() -> None:
    """format_log_entry formats multiple details key-value pairs."""
    log = _make_log(details={"amount": "50", "asset": "TON", "note": "test"})
    result = format_log_entry(log)
    assert "amount" in result
    assert "50" in result
    assert "TON" in result


# ── format_logs_message ────────────────────────────────────────────────────────


def test_format_logs_message_empty_list() -> None:
    """format_logs_message returns 'No logs found' for empty list."""
    result = format_logs_message([])
    assert "No logs found" in result
    assert "Audit Logs" in result


def test_format_logs_message_single_log() -> None:
    """format_logs_message formats one log entry."""
    log = _make_log(action="inject_balance")
    result = format_logs_message([log])
    assert "Recent Admin Actions" in result
    assert "inject_balance" in result


def test_format_logs_message_multiple_logs() -> None:
    """format_logs_message separates multiple entries with newlines."""
    logs = [
        _make_log(action="inject_balance", target_id=1),
        _make_log(action="force_order_status", target_id=2),
    ]
    result = format_logs_message(logs)
    assert "inject_balance" in result
    assert "force_order_status" in result
    # Both entries should be present
    assert result.count("Admin:") == 2
