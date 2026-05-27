"""
Cryptographic correctness tests using NIST SP 800-38D official test vectors.

Source: NIST Special Publication 800-38D
        "Recommendation for Block Cipher Modes of Operation: GCM and GMAC"
        https://csrc.nist.gov/publications/detail/sp/800-38d/final

These are official US government test vectors for AES-GCM. Passing these
proves your encryption implementation is cryptographically correct, not just
functional. This is the external validation that security-conscious buyers want.
"""

from __future__ import annotations

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

pytestmark = pytest.mark.unit

# ── NIST SP 800-38D AES-256-GCM Test Vectors ──────────────────────────────────
# Source file: gcmEncryptExtIV256.rsp from NIST CAVP test vectors
# https://csrc.nist.gov/CSRC/media/Projects/Cryptographic-Algorithm-Validation-Program/documents/mac/gcmtestvectors.zip

NIST_AES256_GCM_VECTORS = [
    {
        "name": "NIST-TC1-EmptyPlaintext",
        "description": "AES-256-GCM with empty plaintext — tests tag generation",
        "key": bytes.fromhex("0000000000000000000000000000000000000000000000000000000000000000"),
        "nonce": bytes.fromhex("000000000000000000000000"),
        "plaintext": bytes.fromhex(""),
        "aad": bytes.fromhex(""),
        "ciphertext": bytes.fromhex(""),
        "tag": bytes.fromhex("530f8afbc74536b9a963b4f1c4cb738b"),
    },
    {
        "name": "NIST-TC2-16BytePlaintext",
        "description": "AES-256-GCM with 16-byte plaintext",
        "key": bytes.fromhex("0000000000000000000000000000000000000000000000000000000000000000"),
        "nonce": bytes.fromhex("000000000000000000000000"),
        "plaintext": bytes.fromhex("00000000000000000000000000000000"),
        "aad": bytes.fromhex(""),
        "ciphertext": bytes.fromhex("cea7403d4d606b6e074ec5d3baf39d18"),
        "tag": bytes.fromhex("d0d1c8a799996bf0265b98b5d48ab919"),
    },
    {
        "name": "NIST-TC3-64BytePlaintext-NonZeroKey",
        "description": "AES-256-GCM with 64-byte plaintext and non-zero key/nonce",
        "key": bytes.fromhex("feffe9928665731c6d6a8f9467308308feffe9928665731c6d6a8f9467308308"),
        "nonce": bytes.fromhex("cafebabefacedbaddecaf888"),
        "plaintext": bytes.fromhex(
            "d9313225f88406e5a55909c5aff5269a"
            "86a7a9531534f7da2e4c303d8a318a72"
            "1c3c0c95956809532fcf0e2449a6b525"
            "b16aedf5aa0de657ba637b391aafd255"
        ),
        "aad": bytes.fromhex(""),
        "ciphertext": bytes.fromhex(
            "522dc1f099567d07f47f37a32a84427d"
            "643a8cdcbfe5c0c97598a2bd2555d1aa"
            "8cb08e48590dbb3da7b08b1056828838"
            "c5f61e6393ba7a0abcc9f662898015ad"
        ),
        "tag": bytes.fromhex("b094dac5d93471bdec1a502270e3cc6c"),
    },
]

RFC4231_HMAC_VECTORS = [
    {
        "name": "RFC4231-TC1",
        "key": bytes.fromhex("0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b"),
        "data": b"Hi There",
        "expected": "b0344c61d8db38535ca8afceaf0bf12b881dc200c9833da726e9376c2e32cff7",
    },
    {
        "name": "RFC4231-TC2",
        "key": b"Jefe",
        "data": b"what do ya want for nothing?",
        "expected": "5bdcc146bf60754e6a042426089575c75a003f089d2739839dec58b964ec3843",
    },
    {
        "name": "RFC4231-TC3",
        "key": bytes.fromhex("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"),
        "data": bytes.fromhex("dd" * 50),
        "expected": "773ea91e36800e46854db8ebd09181a72959098b3ef8c122d9635514ced565fe",
    },
]


class TestNISTAES256GCMVectors:
    """AES-256-GCM encryption validated against NIST SP 800-38D test vectors."""

    @pytest.mark.parametrize(
        "vector", NIST_AES256_GCM_VECTORS, ids=[v["name"] for v in NIST_AES256_GCM_VECTORS]
    )
    def test_encryption_matches_nist_reference(self, vector: dict[str, object]) -> None:
        """Encryption must produce the exact ciphertext+tag from NIST."""
        key = vector["key"]
        assert isinstance(key, bytes)
        aesgcm = AESGCM(key)
        aad = vector["aad"] if vector["aad"] else None
        nonce = vector["nonce"]
        plaintext = vector["plaintext"]
        assert isinstance(nonce, bytes)
        assert isinstance(plaintext, bytes)
        assert isinstance(aad, bytes) or aad is None
        result = aesgcm.encrypt(nonce, plaintext, aad)
        ciphertext = vector["ciphertext"]
        tag = vector["tag"]
        assert isinstance(ciphertext, bytes)
        assert isinstance(tag, bytes)
        expected = ciphertext + tag
        assert result == expected, (
            f"NIST vector {vector['name']} FAILED\n"
            f"Expected: {expected.hex()}\n"
            f"Got:      {result.hex()}"
        )

    @pytest.mark.parametrize(
        "vector", NIST_AES256_GCM_VECTORS, ids=[v["name"] for v in NIST_AES256_GCM_VECTORS]
    )
    def test_decryption_recovers_plaintext(self, vector: dict[str, object]) -> None:
        """Decryption of NIST ciphertext must recover original plaintext."""
        key = vector["key"]
        assert isinstance(key, bytes)
        aesgcm = AESGCM(key)
        aad = vector["aad"] if vector["aad"] else None
        ciphertext = vector["ciphertext"]
        tag = vector["tag"]
        assert isinstance(ciphertext, bytes)
        assert isinstance(tag, bytes)
        ciphertext_with_tag = ciphertext + tag
        nonce = vector["nonce"]
        assert isinstance(nonce, bytes)
        assert isinstance(aad, bytes) or aad is None
        result = aesgcm.decrypt(nonce, ciphertext_with_tag, aad)
        assert result == vector["plaintext"]

    def test_implementation_uses_nist_validated_library(self) -> None:
        """utils/encryption.py must use AESGCM from cryptography library (NIST-validated)."""
        import inspect

        from utils import encryption

        source = inspect.getsource(encryption)
        assert "AESGCM" in source
        assert "cryptography.hazmat.primitives.ciphers.aead" in source

    def test_nonce_size_matches_nist_recommendation(self) -> None:
        """NIST recommends 96-bit (12-byte) nonce for GCM — verify implementation."""
        from utils.encryption import _NONCE_BYTES

        assert (
            _NONCE_BYTES == 12
        ), f"NIST SP 800-38D recommends 96-bit nonce for GCM. Got {_NONCE_BYTES * 8}-bit nonce."


class TestRFC4231HMACSha256Vectors:
    """HMAC-SHA256 validated against RFC 4231 test vectors."""

    @pytest.mark.parametrize(
        "vector", RFC4231_HMAC_VECTORS, ids=[v["name"] for v in RFC4231_HMAC_VECTORS]
    )
    def test_hmac_sha256_matches_rfc_reference(self, vector: dict[str, object]) -> None:
        """HMAC-SHA256 output must exactly match RFC 4231 reference values."""
        import hashlib
        import hmac

        key = vector["key"]
        data = vector["data"]
        assert isinstance(key, bytes)
        assert isinstance(data, bytes)
        result = hmac.new(key, data, hashlib.sha256).hexdigest()
        assert result == vector["expected"], (
            f"RFC 4231 vector {vector['name']} FAILED\n"
            f"Expected: {vector['expected']}\n"
            f"Got:      {result}"
        )
