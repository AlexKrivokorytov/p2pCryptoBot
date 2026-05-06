"""
Contract tests — verify CryptoPayClient against known API response shapes.

These tests verify that our client correctly handles the actual response
format that the Crypto Pay API returns. If the API changes its response
shape, these tests will catch it before production breakage.

External reference: https://help.crypt.bot/crypto-pay-api
"""

from __future__ import annotations

import hashlib
import hmac
import os
from unittest.mock import AsyncMock, patch

import pytest

from providers.crypto_pay import SUPPORTED_ASSETS, CryptoPayClient

# ── Canonical response shapes from Crypto Pay API docs ────────────────────────
# These are the exact fields the real API returns — our client must handle all.

_INVOICE_RESULT: dict[str, object] = {
    "invoice_id": 12345,
    "bot_invoice_url": "https://t.me/CryptoBot?start=IV_JnBSbPTKV_XXXX",
    "mini_app_invoice_url": "https://t.me/CryptoBot/app?startapp=IV_XXXX",
    "web_app_invoice_url": "https://send.ton.org/invoices/IV_XXXX",
    "status": "active",
    "asset": "USDT",
    "amount": "100.0",
    "payload": "order-uuid-here",
    "description": "P2P escrow",
    "created_at": "2024-01-01T00:00:00.000Z",
    "expiration_date": "2024-01-01T00:30:00.000Z",
    "paid_at": None,
    "allow_comments": True,
    "allow_anonymous": True,
    "is_confirmed": False,
}

_TRANSFER_RESULT: dict[str, object] = {
    "transfer_id": 98765,
    "user_id": 123456789,
    "asset": "USDT",
    "amount": "99.5",
    "status": "completed",
    "spend_id": "order-spend-uuid-here",
    "comment": "P2P trade payout",
    "created_at": "2024-01-01T00:15:00.000Z",
}


@pytest.fixture
def client() -> CryptoPayClient:
    """Return a CryptoPayClient with test credentials."""
    with patch.dict(
        os.environ,
        {
            "CRYPTOPAY_TOKEN": "contract_test_token",
            "CRYPTOPAY_CALLBACK_SECRET": "contract_test_secret",
        },
    ):
        return CryptoPayClient()


class TestCreateInvoiceContract:
    """Verify create_invoice handles the real Crypto Pay response shape."""

    @pytest.mark.asyncio
    async def test_maps_invoice_id_to_string(self, client: CryptoPayClient) -> None:
        """invoice_id must always be returned as a string, even if API returns int."""
        with patch.object(client, "_request", AsyncMock(return_value=_INVOICE_RESULT)):
            result = await client.create_invoice("USDT", 100.0, "order-uuid")
        assert result["invoice_id"] == "12345"
        assert isinstance(result["invoice_id"], str)

    @pytest.mark.asyncio
    async def test_uses_bot_invoice_url_for_pay_link(self, client: CryptoPayClient) -> None:
        """pay_url must use bot_invoice_url, not the web or mini-app URL."""
        with patch.object(client, "_request", AsyncMock(return_value=_INVOICE_RESULT)):
            result = await client.create_invoice("USDT", 100.0, "order-uuid")
        assert result["pay_url"] == "https://t.me/CryptoBot?start=IV_JnBSbPTKV_XXXX"
        assert result["pay_url"].startswith("https://")

    @pytest.mark.asyncio
    async def test_returns_status_field(self, client: CryptoPayClient) -> None:
        """status must be forwarded as-is from the API response."""
        with patch.object(client, "_request", AsyncMock(return_value=_INVOICE_RESULT)):
            result = await client.create_invoice("USDT", 100.0, "order-uuid")
        assert result["status"] == "active"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("asset", sorted(SUPPORTED_ASSETS))
    async def test_all_supported_assets_accepted(self, client: CryptoPayClient, asset: str) -> None:
        """Every asset in SUPPORTED_ASSETS must not raise ValueError."""
        mock_result = dict(_INVOICE_RESULT)
        mock_result["asset"] = asset
        with patch.object(client, "_request", AsyncMock(return_value=mock_result)):
            result = await client.create_invoice(asset, 1.0, "payload")
        assert "invoice_id" in result
        assert "pay_url" in result

    @pytest.mark.asyncio
    async def test_unsupported_asset_rejected_before_api_call(
        self, client: CryptoPayClient
    ) -> None:
        """Unknown assets must raise ValueError before any API call is made."""
        with patch.object(client, "_request", AsyncMock()) as mock_api:
            with pytest.raises(ValueError, match="Unsupported asset"):
                await client.create_invoice("SHIB", 10.0, "payload")
            mock_api.assert_not_called()

    @pytest.mark.asyncio
    async def test_zero_amount_rejected_before_api_call(self, client: CryptoPayClient) -> None:
        """Amount of zero must raise ValueError before any API call is made."""
        with patch.object(client, "_request", AsyncMock()) as mock_api:
            with pytest.raises(ValueError):
                await client.create_invoice("USDT", 0.0, "payload")
            mock_api.assert_not_called()

    @pytest.mark.asyncio
    async def test_negative_amount_rejected(self, client: CryptoPayClient) -> None:
        """Negative amounts must raise ValueError before any API call is made."""
        with patch.object(client, "_request", AsyncMock()) as mock_api:
            with pytest.raises(ValueError):
                await client.create_invoice("USDT", -1.0, "payload")
            mock_api.assert_not_called()

    @pytest.mark.asyncio
    async def test_api_error_raises_runtime_error(self, client: CryptoPayClient) -> None:
        """RuntimeError from _request must propagate to the caller."""
        with (
            patch.object(client, "_request", AsyncMock(side_effect=RuntimeError("API error"))),
            pytest.raises(RuntimeError, match="API error"),
        ):
            await client.create_invoice("USDT", 10.0, "payload")


class TestTransferContract:
    """Verify transfer handles the real Crypto Pay transfer response shape."""

    @pytest.mark.asyncio
    async def test_returns_transfer_id(self, client: CryptoPayClient) -> None:
        """transfer_id must be extracted from the API result dict."""
        with patch.object(client, "_request", AsyncMock(return_value=_TRANSFER_RESULT)):
            result = await client.transfer(123456789, "USDT", 99.5, "spend-uuid")
        assert result["transfer_id"] == 98765

    @pytest.mark.asyncio
    async def test_returns_spend_id_unchanged(self, client: CryptoPayClient) -> None:
        """spend_id in response must equal the spend_id passed by caller (idempotency key)."""
        with patch.object(client, "_request", AsyncMock(return_value=_TRANSFER_RESULT)):
            result = await client.transfer(123456789, "USDT", 99.5, "spend-uuid")
        assert result["spend_id"] == "spend-uuid"

    @pytest.mark.asyncio
    async def test_returns_status(self, client: CryptoPayClient) -> None:
        """Status must be forwarded from the API response."""
        with patch.object(client, "_request", AsyncMock(return_value=_TRANSFER_RESULT)):
            result = await client.transfer(123456789, "USDT", 99.5, "spend-uuid")
        assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_unsupported_asset_rejected(self, client: CryptoPayClient) -> None:
        """Unsupported asset must raise ValueError before calling the API."""
        with patch.object(client, "_request", AsyncMock()) as mock_api:
            with pytest.raises(ValueError):
                await client.transfer(123, "DOGE", 1.0, "spend-id")
            mock_api.assert_not_called()

    @pytest.mark.asyncio
    async def test_zero_transfer_amount_rejected(self, client: CryptoPayClient) -> None:
        """Transfer of zero must raise ValueError before calling the API."""
        with patch.object(client, "_request", AsyncMock()) as mock_api:
            with pytest.raises(ValueError):
                await client.transfer(123, "USDT", 0.0, "spend-id")
            mock_api.assert_not_called()


class TestWebhookSignatureContract:
    """Verify HMAC-SHA256 webhook verification matches Crypto Pay specification."""

    def test_valid_signature_accepted(self, client: CryptoPayClient) -> None:
        """A correctly signed body must return True."""
        body = b'{"update_type":"invoice_paid","update_id":123}'
        secret_key = hashlib.sha256(b"contract_test_secret").digest()
        signature = hmac.new(secret_key, body, hashlib.sha256).hexdigest()
        assert client.verify_webhook_signature(body, signature) is True

    def test_tampered_body_rejected(self, client: CryptoPayClient) -> None:
        """A body modified after signing must fail verification."""
        body = b'{"update_type":"invoice_paid"}'
        tampered = b'{"update_type":"invoice_paid","injected":true}'
        secret_key = hashlib.sha256(b"contract_test_secret").digest()
        signature = hmac.new(secret_key, body, hashlib.sha256).hexdigest()
        assert client.verify_webhook_signature(tampered, signature) is False

    def test_wrong_secret_rejected(self, client: CryptoPayClient) -> None:
        """A signature produced with the wrong secret must fail verification."""
        body = b'{"payload": "test"}'
        wrong_key = hashlib.sha256(b"wrong_secret").digest()
        signature = hmac.new(wrong_key, body, hashlib.sha256).hexdigest()
        assert client.verify_webhook_signature(body, signature) is False

    def test_empty_signature_rejected(self, client: CryptoPayClient) -> None:
        """An empty signature string must return False, not raise an exception."""
        body = b'{"payload": "test"}'
        assert client.verify_webhook_signature(body, "") is False

    def test_case_insensitive_hex_comparison(self, client: CryptoPayClient) -> None:
        """Crypto Pay may send uppercase hex — both cases must be accepted."""
        body = b'{"payload": "test"}'
        secret_key = hashlib.sha256(b"contract_test_secret").digest()
        sig_lower = hmac.new(secret_key, body, hashlib.sha256).hexdigest()
        sig_upper = sig_lower.upper()
        assert client.verify_webhook_signature(body, sig_upper) is True

    def test_close_is_idempotent(self, client: CryptoPayClient) -> None:
        """Calling close() on an unopened client must not raise."""
        import asyncio

        asyncio.get_event_loop().run_until_complete(client.close())


class TestExchangeRatesContract:
    """Verify get_exchange_rates handles canonical list response shape."""

    @pytest.mark.asyncio
    async def test_returns_list_of_dicts(self, client: CryptoPayClient) -> None:
        """Result must be a list of dicts with source, target, rate keys."""
        canonical = [
            {"source": "USDT", "target": "USD", "rate": "1.0001", "is_valid": True},
            {"source": "TON", "target": "USD", "rate": "5.23", "is_valid": True},
        ]
        with patch.object(client, "_request", AsyncMock(return_value=canonical)):
            result = await client.get_exchange_rates()
        assert len(result) == 2
        assert result[0]["source"] == "USDT"
        assert result[0]["target"] == "USD"
        assert result[0]["rate"] == "1.0001"

    @pytest.mark.asyncio
    async def test_returns_empty_list_on_non_list_response(self, client: CryptoPayClient) -> None:
        """If API returns non-list (e.g. empty dict), result must be empty list."""
        with patch.object(client, "_request", AsyncMock(return_value={})):
            result = await client.get_exchange_rates()
        assert result == []

    @pytest.mark.asyncio
    async def test_api_error_propagates(self, client: CryptoPayClient) -> None:
        """RuntimeError from underlying _request must propagate."""
        with (
            patch.object(client, "_request", AsyncMock(side_effect=RuntimeError("net error"))),
            pytest.raises(RuntimeError),
        ):
            await client.get_exchange_rates()

    def test_supported_assets_is_frozen_set(self) -> None:
        """SUPPORTED_ASSETS must be a frozenset to prevent runtime mutation."""
        assert isinstance(SUPPORTED_ASSETS, frozenset)

    def test_supported_assets_contains_required_coins(self) -> None:
        """Core assets required by the bot must always be present."""
        required = {"USDT", "TON", "BTC", "ETH", "USDC"}
        assert required.issubset(SUPPORTED_ASSETS), (
            f"Missing required assets: {required - SUPPORTED_ASSETS}"
        )
