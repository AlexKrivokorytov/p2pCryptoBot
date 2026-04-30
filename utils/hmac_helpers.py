"""HMAC helpers — constant-time comparison for webhook signature validation."""

from __future__ import annotations

import hashlib
import hmac


def compare_hmac(expected: str, actual: str) -> bool:
    """Compare two HMAC hex strings in constant time.

    Prevents timing-based side-channel attacks.

    Args:
        expected: The HMAC we computed.
        actual: The HMAC supplied by the caller / webhook header.

    Returns:
        ``True`` if both strings match, ``False`` otherwise.
    """
    return hmac.compare_digest(expected.lower(), actual.lower())


def compute_hmac_sha256(secret: str, body: bytes) -> str:
    """Compute an HMAC-SHA256 hex digest.

    The secret is first hashed with SHA-256 before use as the HMAC key,
    matching the Crypto Pay webhook verification algorithm.

    Args:
        secret: Raw secret string (e.g. ``CRYPTOPAY_CALLBACK_SECRET``).
        body: Raw request body bytes.

    Returns:
        Lowercase hex digest string.
    """
    secret_key = hashlib.sha256(secret.encode()).digest()
    return hmac.new(secret_key, body, hashlib.sha256).hexdigest()
