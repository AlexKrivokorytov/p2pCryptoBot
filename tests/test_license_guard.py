"""Tests for utils.license_guard — license key generation and validation."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from utils.license_guard import (
    check_license_or_abort,
    generate_license_key,
    validate_license,
)

BOT_TOKEN = "1234567890:ABCDEFabcdefGHIJKL"
SELLER_SECRET = "test_seller_secret_for_ci_only_1234"


class TestGetSellerSecret:
    """Test _get_seller_secret internal function via public APIs."""

    def test_generate_key_without_seller_secret_raises(self) -> None:
        """generate_license_key should raise RuntimeError if SELLER_SECRET is not set."""
        with patch.dict(os.environ, {}, clear=True), pytest.raises(
            RuntimeError, match="SELLER_SECRET"
        ):
            os.environ.pop("SELLER_SECRET", None)
            generate_license_key(BOT_TOKEN)


class TestGenerateLicenseKey:
    """Test HMAC key generation."""

    def test_generate_key_returns_hex(self) -> None:
        """generate_license_key should return a 64-char hex string."""
        with patch.dict(os.environ, {"SELLER_SECRET": SELLER_SECRET}):
            key = generate_license_key(BOT_TOKEN)
        assert len(key) == 64
        assert all(c in "0123456789abcdef" for c in key)

    def test_generate_key_is_deterministic(self) -> None:
        """Same inputs should produce same output (HMAC is deterministic)."""
        with patch.dict(os.environ, {"SELLER_SECRET": SELLER_SECRET}):
            key1 = generate_license_key(BOT_TOKEN)
            key2 = generate_license_key(BOT_TOKEN)
        assert key1 == key2

    def test_different_tokens_produce_different_keys(self) -> None:
        """Different bot tokens must yield different keys."""
        with patch.dict(os.environ, {"SELLER_SECRET": SELLER_SECRET}):
            key1 = generate_license_key(BOT_TOKEN)
            key2 = generate_license_key("9999999999:ZZZZZZzzzzzzZZZZZZ")
        assert key1 != key2


class TestValidateLicense:
    """Test license validation logic."""

    def test_valid_license_returns_true(self) -> None:
        """validate_license should return True for a correctly generated key."""
        with patch.dict(os.environ, {"SELLER_SECRET": SELLER_SECRET}):
            key = generate_license_key(BOT_TOKEN)
            result = validate_license(BOT_TOKEN, key)
        assert result is True

    def test_wrong_key_returns_false(self) -> None:
        """validate_license should return False for a bad key."""
        with patch.dict(os.environ, {"SELLER_SECRET": SELLER_SECRET}):
            result = validate_license(BOT_TOKEN, "deadbeef" * 8)
        assert result is False

    def test_strips_whitespace_from_key(self) -> None:
        """validate_license should handle keys with surrounding whitespace."""
        with patch.dict(os.environ, {"SELLER_SECRET": SELLER_SECRET}):
            key = generate_license_key(BOT_TOKEN)
            result = validate_license(BOT_TOKEN, "  " + key + "  ")
        assert result is True


class TestCheckLicenseOrAbort:
    """Test the startup enforcement function."""

    def test_skips_if_no_seller_secret(self) -> None:
        """check_license_or_abort should not raise if SELLER_SECRET is unset."""
        env = {"SELLER_SECRET": "", "LICENSE_KEY": ""}
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("SELLER_SECRET", None)
            # Must not raise
            check_license_or_abort(BOT_TOKEN)

    def test_raises_system_exit_if_license_key_missing(self) -> None:
        """If SELLER_SECRET is set but LICENSE_KEY is absent → SystemExit."""
        env = {"SELLER_SECRET": SELLER_SECRET, "LICENSE_KEY": ""}
        with patch.dict(os.environ, env, clear=False), pytest.raises(SystemExit):
            os.environ.pop("LICENSE_KEY", None)
            check_license_or_abort(BOT_TOKEN)

    def test_raises_system_exit_if_license_key_invalid(self) -> None:
        """If LICENSE_KEY doesn't match BOT_TOKEN → SystemExit."""
        env = {"SELLER_SECRET": SELLER_SECRET, "LICENSE_KEY": "wrongkey" * 8}
        with patch.dict(os.environ, env), pytest.raises(SystemExit):
            check_license_or_abort(BOT_TOKEN)

    def test_passes_with_valid_license(self) -> None:
        """check_license_or_abort should not raise with a valid license."""
        with patch.dict(os.environ, {"SELLER_SECRET": SELLER_SECRET}):
            key = generate_license_key(BOT_TOKEN)
        env = {"SELLER_SECRET": SELLER_SECRET, "LICENSE_KEY": key}
        with patch.dict(os.environ, env):
            check_license_or_abort(BOT_TOKEN)  # Should not raise
