"""AES-256-GCM encryption/decryption for secrets stored in the DB.

The AES key is read from the ``AES_KEY`` environment variable (64-char hex = 32 bytes).

Usage::

    enc = encrypt("my-secret-api-key")   # returns hex string
    plain = decrypt(enc)                  # returns original string
"""

from __future__ import annotations

import os
import secrets

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_NONCE_BYTES = 12  # 96-bit nonce — standard for GCM


def _get_key() -> bytes:
    """Load and validate the AES-256 key from environment.

    Returns:
        32-byte key.

    Raises:
        ValueError: If ``AES_KEY`` is missing or not a valid 64-char hex string.
    """
    raw = os.environ.get("AES_KEY", "")
    if len(raw) != 64:
        raise ValueError(
            "AES_KEY must be a 64-character hex string (32 bytes). "
            "Generate with: python -c \"import secrets; print(secrets.token_hex(32))\""
        )
    return bytes.fromhex(raw)


def encrypt(plaintext: str) -> str:
    """Encrypt *plaintext* with AES-256-GCM.

    A random 12-byte nonce is prepended to the ciphertext.

    Args:
        plaintext: String to encrypt.

    Returns:
        Hex-encoded string: ``nonce (24 hex chars) + ciphertext``.
    """
    key = _get_key()
    nonce = secrets.token_bytes(_NONCE_BYTES)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode(), None)
    return (nonce + ciphertext).hex()


def decrypt(token: str) -> str:
    """Decrypt a hex-encoded AES-256-GCM ciphertext.

    Args:
        token: Hex string produced by :func:`encrypt`.

    Returns:
        Original plaintext string.

    Raises:
        ValueError: If the token is malformed.
        cryptography.exceptions.InvalidTag: If decryption fails (tampered data).
    """
    try:
        raw = bytes.fromhex(token)
    except ValueError as exc:
        raise ValueError(f"Invalid encrypted token (not hex): {exc}") from exc

    nonce = raw[:_NONCE_BYTES]
    ciphertext = raw[_NONCE_BYTES:]
    key = _get_key()
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ciphertext, None).decode()
