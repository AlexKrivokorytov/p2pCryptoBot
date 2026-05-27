"""
Security assertion tests — verify security properties hold across the codebase.

These are not unit tests. They test structural security properties:
- AES nonce uniqueness (prevents nonce reuse attacks)
- HMAC uses compare_digest (prevents timing attacks)
- No raw SQL in services (prevents SQL injection)
- Pessimistic locking in all financial operations
- Private keys encrypted before storage
- No secrets in log output
"""

from __future__ import annotations

import os
import pathlib
import secrets
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.unit


class TestAESSecurityProperties:
    def test_nonce_is_unique_per_encryption(self) -> None:
        """100 encryptions of the same plaintext must produce 100 different tokens."""
        key = secrets.token_hex(32)
        with patch.dict(os.environ, {"AES_KEY": key}):
            from utils.encryption import encrypt

            tokens = [encrypt("same-plaintext-value") for _ in range(100)]
        assert len(set(tokens)) == 100, "CRITICAL: Nonce reuse detected"

    def test_nonce_size_is_96_bits(self) -> None:
        from utils.encryption import _NONCE_BYTES

        assert _NONCE_BYTES == 12

    def test_authentication_tag_detects_tampering(self) -> None:
        from cryptography.exceptions import InvalidTag

        key = secrets.token_hex(32)
        with patch.dict(os.environ, {"AES_KEY": key}):
            from utils.encryption import decrypt, encrypt

            token = encrypt("wallet-private-key-data")
            raw = bytes.fromhex(token)
            # Flip one byte in ciphertext portion
            tampered = raw[:12] + bytes([raw[12] ^ 0xFF]) + raw[13:]
            with pytest.raises((InvalidTag, Exception)):
                decrypt(tampered.hex())

    def test_wrong_key_cannot_decrypt(self) -> None:
        from cryptography.exceptions import InvalidTag

        key_a = secrets.token_hex(32)
        key_b = secrets.token_hex(32)
        assert key_a != key_b

        with patch.dict(os.environ, {"AES_KEY": key_a}):
            from utils import encryption as enc_module

            # Reset cache to force re-read
            token = enc_module.encrypt("secret-api-key")

        with (
            patch.dict(os.environ, {"AES_KEY": key_b}),
            pytest.raises((InvalidTag, Exception)),
        ):
            enc_module.decrypt(token)

    def test_plaintext_not_visible_in_encrypted_output(self) -> None:
        key = secrets.token_hex(32)
        plaintext = "user-binance-api-key-secretvalue123"
        with patch.dict(os.environ, {"AES_KEY": key}):
            from utils.encryption import encrypt

            token = encrypt(plaintext)
        assert plaintext not in token
        assert plaintext.encode().hex() not in token


class TestHMACSecurityProperties:
    def test_compare_digest_used_not_equality_operator(self) -> None:
        """HMAC comparison must use compare_digest to prevent timing attacks."""
        import inspect

        from utils import hmac_helpers

        source = inspect.getsource(hmac_helpers.compare_hmac)
        assert "compare_digest" in source

    def test_hmac_uses_sha256_not_weak_hash(self) -> None:
        import inspect

        from utils import hmac_helpers

        source = inspect.getsource(hmac_helpers)
        assert "sha256" in source
        assert "md5" not in source.lower()
        assert "sha1" not in source.lower()


class TestSQLInjectionPrevention:
    def test_no_raw_sql_formatting_in_services(self) -> None:
        """Services must never format user data into SQL strings."""
        dangerous_patterns = [
            'f"SELECT',
            "f'SELECT",
            'f"UPDATE',
            "f'UPDATE",
            'f"INSERT',
            "f'INSERT",
            'f"DELETE',
            "f'DELETE",
            "% (user",
        ]
        for py_file in pathlib.Path("services").rglob("*.py"):
            source = py_file.read_text()
            for pattern in dangerous_patterns:
                assert pattern not in source, f"Potential SQL injection in {py_file}: {pattern!r}"

    def test_pessimistic_locking_in_financial_services(self) -> None:
        """All services that modify financial state must use with_for_update()."""
        critical_files = [
            "services/order_service.py",
            "services/escrow_service.py",
            "services/dispute_service.py",
        ]
        for path in critical_files:
            source = pathlib.Path(path).read_text()
            assert (
                "with_for_update()" in source
            ), f"{path} missing with_for_update() — race condition risk"


class TestSecretManagement:
    def test_private_keys_encrypted_before_db_storage(self) -> None:
        import inspect

        from services import wallet_service

        source = inspect.getsource(wallet_service.generate_and_save_wallet)
        assert "encrypt(" in source
        encrypt_pos = source.index("encrypt(")
        wallet_pos = source.index("UserWallet(")
        assert (
            encrypt_pos < wallet_pos
        ), "Private key must be encrypted BEFORE creating UserWallet object"

    def test_no_private_key_in_log_statements(self) -> None:
        """Private key material must never appear in log calls."""
        for py_file in pathlib.Path("services").rglob("*.py"):
            source = py_file.read_text()
            lines = source.split("\n")
            for line in lines:
                if "log." in line:
                    low = line.lower()
                    assert "private_key" not in low
                    assert "mnemonic" not in low
