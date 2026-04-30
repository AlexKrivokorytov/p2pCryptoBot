"""Tests for encryption utils — full coverage including error paths."""

from __future__ import annotations

import os
import secrets
from unittest.mock import patch

import pytest

from utils import encryption


VALID_KEY = secrets.token_hex(32)  # 64-char hex string


# ── _get_key ──────────────────────────────────────────────────────────────────

def test_get_key_missing_raises() -> None:
    """_get_key raises ValueError when AES_KEY env is missing."""
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(ValueError, match="AES_KEY must be"):
            encryption._get_key()


def test_get_key_wrong_length_raises() -> None:
    """_get_key raises ValueError when AES_KEY is not 64 hex chars."""
    with patch.dict(os.environ, {"AES_KEY": "tooshort"}):
        with pytest.raises(ValueError, match="AES_KEY must be"):
            encryption._get_key()


def test_get_key_valid() -> None:
    """_get_key returns 32 bytes for a valid 64-char hex AES_KEY."""
    with patch.dict(os.environ, {"AES_KEY": VALID_KEY}):
        key = encryption._get_key()
    assert len(key) == 32
    assert isinstance(key, bytes)


# ── encrypt / decrypt ─────────────────────────────────────────────────────────

def test_encrypt_returns_hex_string() -> None:
    """encrypt returns a non-empty hex string."""
    with patch.dict(os.environ, {"AES_KEY": VALID_KEY}):
        token = encryption.encrypt("hello-world")
    assert isinstance(token, str)
    assert len(token) > 0
    # Should be valid hex
    bytes.fromhex(token)


def test_decrypt_roundtrip() -> None:
    """encrypt → decrypt returns the original plaintext."""
    plaintext = "my-secret-exchange-api-key-12345"
    with patch.dict(os.environ, {"AES_KEY": VALID_KEY}):
        token = encryption.encrypt(plaintext)
        result = encryption.decrypt(token)
    assert result == plaintext


def test_decrypt_invalid_hex_raises() -> None:
    """decrypt raises ValueError for non-hex input."""
    with patch.dict(os.environ, {"AES_KEY": VALID_KEY}):
        with pytest.raises(ValueError, match="Invalid encrypted token"):
            encryption.decrypt("NOT_HEX_$$$$")


def test_encrypt_unique_nonce() -> None:
    """Two encryptions of the same text produce different tokens (unique nonces)."""
    text = "same-plaintext"
    with patch.dict(os.environ, {"AES_KEY": VALID_KEY}):
        token1 = encryption.encrypt(text)
        token2 = encryption.encrypt(text)
    assert token1 != token2, "Tokens must differ due to random nonces"


def test_decrypt_tampered_ciphertext_raises() -> None:
    """decrypt raises an error when ciphertext has been tampered with."""
    from cryptography.exceptions import InvalidTag
    with patch.dict(os.environ, {"AES_KEY": VALID_KEY}):
        token = encryption.encrypt("original")
        # Tamper with the ciphertext bytes (skip first 24 chars = nonce)
        nonce_hex = token[:24]
        tampered = nonce_hex + "ff" * ((len(token) - 24) // 2)
        with pytest.raises((InvalidTag, Exception)):
            encryption.decrypt(tampered)


# ── datetime_helpers — missing lines 28, 45 ───────────────────────────────────

def test_is_order_expired_naive_datetime() -> None:
    """is_order_expired handles naive (tz-unaware) created_at correctly."""
    from datetime import datetime, timezone, timedelta
    from unittest.mock import MagicMock
    from utils.datetime_helpers import is_order_expired

    order = MagicMock()
    # Naive datetime (no tzinfo) — covers line 28
    order.created_at = datetime.utcnow() - timedelta(seconds=2000)

    result = is_order_expired(order, timeout_sec=1800)
    assert result is True


def test_seconds_until_expiry_naive_datetime() -> None:
    """seconds_until_expiry handles naive created_at (covers line 45)."""
    from datetime import datetime, timedelta
    from unittest.mock import MagicMock
    from utils.datetime_helpers import seconds_until_expiry

    order = MagicMock()
    # Naive datetime set in the future
    order.created_at = datetime.utcnow()

    result = seconds_until_expiry(order, timeout_sec=1800)
    assert isinstance(result, int)
    assert result >= 0


def test_seconds_until_expiry_already_expired() -> None:
    """seconds_until_expiry returns 0 when order is already expired."""
    from datetime import datetime, timedelta
    from unittest.mock import MagicMock
    from utils.datetime_helpers import seconds_until_expiry

    order = MagicMock()
    order.created_at = datetime.utcnow() - timedelta(seconds=5000)

    result = seconds_until_expiry(order, timeout_sec=1800)
    assert result == 0
