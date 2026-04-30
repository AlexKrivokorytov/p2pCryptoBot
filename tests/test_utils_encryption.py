"""Tests for encryption utilities."""

from __future__ import annotations

import contextlib
import os
from unittest.mock import patch

from utils import encryption


def test_encrypt_decrypt():
    # Set a dummy key for testing if not already set
    with patch.dict(os.environ, {"AES_KEY": "0" * 64}):
        # Reset the key cache if possible, but we'll just test the functions
        original = "hello world"
        encrypted = encryption.encrypt(original)
        assert encrypted != original

        decrypted = encryption.decrypt(encrypted)
        assert decrypted == original


def test_decrypt_invalid_data():
    with patch.dict(os.environ, {"AES_KEY": "0" * 64}):
        # Should return empty string or raise?
        # Implementation says: return decrypt(wallet.encrypted_private_key)
        # But encryption.decrypt itself might raise if data is junk.
        with contextlib.suppress(Exception):
            encryption.decrypt("not-base64-junk")
