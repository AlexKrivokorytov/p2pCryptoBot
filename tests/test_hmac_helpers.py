"""Tests for HMAC helpers — 100% coverage of compare_hmac and compute_hmac_sha256."""

from __future__ import annotations

import hashlib
import hmac

from utils.hmac_helpers import compare_hmac, compute_hmac_sha256

# ── compare_hmac ──────────────────────────────────────────────────────────────


def test_compare_hmac_equal() -> None:
    """Returns True for identical HMAC strings."""
    sig = "abc123def456"
    assert compare_hmac(sig, sig) is True


def test_compare_hmac_different() -> None:
    """Returns False for different HMAC strings."""
    assert compare_hmac("aaaaaa", "bbbbbb") is False


def test_compare_hmac_case_insensitive() -> None:
    """Comparison is case-insensitive (upper vs lower hex)."""
    assert compare_hmac("ABCDEF", "abcdef") is True


def test_compare_hmac_empty_strings() -> None:
    """Two empty strings compare as equal."""
    assert compare_hmac("", "") is True


def test_compare_hmac_one_empty() -> None:
    """Empty vs non-empty string returns False."""
    assert compare_hmac("abc", "") is False


# ── compute_hmac_sha256 ───────────────────────────────────────────────────────


def test_compute_hmac_sha256_returns_hex_string() -> None:
    """Returns a lowercase hex string of length 64 (SHA-256 digest)."""
    result = compute_hmac_sha256("my-secret", b'{"payload": "test"}')
    assert isinstance(result, str)
    assert len(result) == 64
    assert result == result.lower()


def test_compute_hmac_sha256_deterministic() -> None:
    """Same secret + body always produces the same digest."""
    secret = "crypto-pay-secret"
    body = b'{"status": "paid"}'
    result1 = compute_hmac_sha256(secret, body)
    result2 = compute_hmac_sha256(secret, body)
    assert result1 == result2


def test_compute_hmac_sha256_different_body() -> None:
    """Different body produces a different digest."""
    secret = "my-secret"
    r1 = compute_hmac_sha256(secret, b"body-one")
    r2 = compute_hmac_sha256(secret, b"body-two")
    assert r1 != r2


def test_compute_hmac_sha256_different_secret() -> None:
    """Different secret produces a different digest for same body."""
    body = b'{"payload": "order-uuid"}'
    r1 = compute_hmac_sha256("secret-a", body)
    r2 = compute_hmac_sha256("secret-b", body)
    assert r1 != r2


def test_compute_hmac_sha256_matches_manual_calculation() -> None:
    """Output matches a manually computed HMAC-SHA256 using the same algorithm."""
    secret = "test-secret"
    body = b"webhook-body"

    # Manually reproduce the algorithm
    secret_key = hashlib.sha256(secret.encode()).digest()
    expected = hmac.new(secret_key, body, hashlib.sha256).hexdigest()

    result = compute_hmac_sha256(secret, body)
    assert result == expected


def test_compute_hmac_sha256_empty_body() -> None:
    """Computes a valid digest even for empty body bytes."""
    result = compute_hmac_sha256("secret", b"")
    assert len(result) == 64


def test_compute_hmac_sha256_unicode_secret() -> None:
    """Handles Unicode secret strings without raising."""
    result = compute_hmac_sha256("сек₽рет", b"body")
    assert len(result) == 64
