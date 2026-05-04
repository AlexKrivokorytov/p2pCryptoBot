"""Crypto Pay provider — thin async wrapper around aiocryptopay.

Handles invoice creation, transfers (with idempotency), exchange rates,
and HMAC-SHA256 webhook signature verification.
"""

from __future__ import annotations

import hashlib
import hmac
from typing import Any

import structlog
from aiocryptopay import AioCryptoPay, Networks

log = structlog.get_logger(__name__)

# Validated asset list — must match SupportedAsset enum in db/models/order.py
SUPPORTED_ASSETS: frozenset[str] = frozenset({"BTC", "TON", "USDT", "USDC", "ETH"})


class CryptoPayClient:
    """Async Crypto Pay client with idempotent transfers and HMAC verification.

    Usage::

        client = CryptoPayClient()
        invoice = await client.create_invoice("USDT", 100.0, "order:uuid-here")
        ok = client.verify_webhook_signature(raw_body_bytes, header_signature)
        await client.transfer(user_id=123, asset="USDT", amount=99.5, spend_id="uuid")
    """

    def __init__(self) -> None:
        from bot.config import get_settings

        settings = get_settings()
        token = settings.CRYPTOPAY_TOKEN
        self._callback_secret = settings.CRYPTOPAY_CALLBACK_SECRET
        # Use MAIN network; switch to TESTNET for development
        self._api = AioCryptoPay(token=token, network=Networks.MAIN_NET)

    # ── Invoice ────────────────────────────────────────────────────────────────

    async def create_invoice(
        self,
        asset: str,
        amount: float,
        payload: str,
    ) -> dict[str, Any]:
        """Create a Crypto Pay invoice.

        Args:
            asset: Crypto asset ticker, e.g. "USDT". Must be in SUPPORTED_ASSETS.
            amount: Amount of crypto to request.
            payload: Arbitrary string payload stored in the invoice
                     (use the order UUID so the webhook can correlate it).

        Returns:
            Dict containing at least ``invoice_id`` and ``pay_url``.

        Raises:
            ValueError: If *asset* is not in the supported list.
        """
        if asset not in SUPPORTED_ASSETS:
            raise ValueError(f"Unsupported asset: {asset!r}. Allowed: {SUPPORTED_ASSETS}")
        if amount <= 0:
            raise ValueError(f"Amount must be positive, got {amount}")

        invoice = await self._api.create_invoice(
            asset=asset,
            amount=amount,
            payload=payload,
            expires_in=1800,  # 30 minutes — matches ORDER_TIMEOUT_SEC
        )
        log.info(
            "cryptopay_invoice_created",
            asset=asset,
            amount=amount,
            invoice_id=invoice.invoice_id,
            status="ok",
        )
        return {
            "invoice_id": str(invoice.invoice_id),
            "pay_url": invoice.bot_invoice_url,
            "status": invoice.status,
        }

    # ── Transfer ───────────────────────────────────────────────────────────────

    async def transfer(
        self,
        user_id: int,
        asset: str,
        amount: float,
        spend_id: str,
    ) -> dict[str, Any]:
        """Transfer crypto to a Telegram user via Crypto Pay.

        Idempotent: callers must supply a stable *spend_id* derived from the
        order UUID so that a duplicate call (e.g. after a crash) is safe to
        retry — Crypto Pay will reject duplicates with the same spend_id.

        Args:
            user_id: Recipient Telegram user ID.
            asset: Crypto asset ticker.
            amount: Amount to transfer.
            spend_id: Unique string per transfer (use order UUID).

        Returns:
            Dict with transfer details from Crypto Pay.

        Raises:
            ValueError: If *asset* is not supported or *amount* is non-positive.
        """
        if asset not in SUPPORTED_ASSETS:
            raise ValueError(f"Unsupported asset: {asset!r}")
        if amount <= 0:
            raise ValueError(f"Transfer amount must be positive, got {amount}")

        transfer = await self._api.transfer(
            user_id=user_id,
            asset=asset,
            amount=amount,
            spend_id=spend_id,
        )
        log.info(
            "cryptopay_transfer_sent",
            user_id=user_id,
            asset=asset,
            amount=amount,
            spend_id=spend_id,
            transfer_id=getattr(transfer, "transfer_id", None),
            status="ok",
        )
        return {
            "transfer_id": getattr(transfer, "transfer_id", None),
            "spend_id": spend_id,
            "status": getattr(transfer, "status", "unknown"),
        }

    # ── Exchange rates ─────────────────────────────────────────────────────────

    async def get_exchange_rates(self) -> list[dict[str, Any]]:
        """Fetch current exchange rates from Crypto Pay.

        Returns:
            List of rate dicts: ``[{"source": "USDT", "target": "USD", "rate": "1.0"}, ...]``.
        """
        rates = await self._api.get_exchange_rates()
        return [
            {
                "source": r.source,
                "target": r.target,
                "rate": r.rate,
            }
            for r in rates
        ]

    # ── Webhook signature verification ─────────────────────────────────────────

    def verify_webhook_signature(self, body: bytes, signature: str) -> bool:
        """Verify the HMAC-SHA256 signature of an incoming Crypto Pay webhook.

        Compares in constant time to prevent timing attacks.

        Args:
            body: Raw request body bytes.
            signature: Value of the ``crypto-pay-api-signature`` header.

        Returns:
            ``True`` if the signature is valid, ``False`` otherwise.
        """
        secret_key = hashlib.sha256(self._callback_secret.encode()).digest()
        expected = hmac.new(secret_key, body, hashlib.sha256).hexdigest()  # nosec B303
        valid = hmac.compare_digest(expected, signature.lower())
        if not valid:
            log.warning(
                "webhook_hmac_failed",
                status="invalid_signature",
            )
        return valid

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    async def close(self) -> None:
        """Close the underlying aiohttp session."""
        await self._api.close()
