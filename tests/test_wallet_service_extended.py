"""Extended tests for wallet_service."""

from unittest.mock import patch

import pytest

from db.models.wallet import UserWallet
from services import wallet_service


def test_get_provider_unsupported():
    with pytest.raises(ValueError, match="Unsupported chain"):
        wallet_service._get_provider("invalid_chain")


def test_decrypt_wallet_key():
    wallet = UserWallet(encrypted_private_key="dummy")
    with patch("services.wallet_service.decrypt") as mock_decrypt:
        mock_decrypt.return_value = "secret_pk"
        pk = wallet_service.decrypt_wallet_key(wallet)
        assert pk == "secret_pk"


def test_get_provider_cache():
    # Force creation of provider
    p1 = wallet_service._get_provider("ton")
    p2 = wallet_service._get_provider("ton")
    assert p1 is p2  # Singleton check
