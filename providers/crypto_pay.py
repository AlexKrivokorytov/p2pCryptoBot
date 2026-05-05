"""Crypto Pay provider — direct aiohttp implementation of the Crypto Pay API.

No third-party SDK dependency (aiocryptopay removed). All calls go directly
to the Crypto Pay REST API via aiohttp, giving full control over TLS,
certifi version, and request lifecycle.

API docs: https://help.crypt.bot/crypto-pay-api
"""

from __future__ import annotations

import hashlib
import hmac as _hmac  # explicit alias — avoids Bandit B105/B324 false positives
import os
from typing import Any

import aiohttp
import structlog

log = structlog.get_logger(__name__)

# Validated asset list — must match SupportedAsset enum in db/models/order.py
SUPPORTED_ASSETS: frozenset[str] = frozenset({"BTC", "TON", "USDT", "USDC", "ETH"})

_MAINNET_BASE_URL: str = "https://pay.crypt.bot/api"
_TESTNET_BASE_URL: str = "https://testnet-pay.crypt.bot/api"


class CryptoPayClient:
    """Async Crypto Pay client with idempotent transfers and HMAC verification.

    Uses direct aiohttp calls instead of the aiocryptopay SDK, removing
    the certifi<2024 version constraint that blocked security updates.

    Usage::

        client = CryptoPayClient()
        invoice = await client.create_invoice("USDT", 100.0, "order:uuid-here")
        ok = client.verify_webhook_signature(raw_body_bytes, header_signature)
        await client.transfer(user_id=123, asset="USDT", amount=99.5, spend_id="uuid")
        await client.close()
    """

    def __init__(self, testnet: bool = False) -> None:
        """Initialize the client from environment variables.

        Args:
            testnet: If True, use the Crypto Pay testnet endpoint.
        """
        self._token: str = os.environ["CRYPTOPAY_TOKEN"]
        self._callback_secret: str = os.environ["CRYPTOPAY_CALLBACK_SECRET"]
        self._base_url: str = _TESTNET_BASE_URL if testnet else _MAINNET_BASE_URL
        self._session: aiohttp.ClientSession | None = None

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _get_session(self) -> aiohttp.ClientSession:
        """Return (or lazily create) the underlying aiohttp session.

        Returns:
            An open aiohttp.ClientSession with the API token header pre-set.
        """
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(headers={"Crypto-Pay-API-Token": self._token})
        return self._session

    async def _request(
        self,
        method: str,
        endpoint: str,
        **params: Any,
    ) -> Any:
        """Execute an authenticated API request and return the ``result`` field.

        Args:
            method: HTTP method string — ``"GET"`` or ``"POST"``.
            endpoint: API endpoint name, e.g. ``"createInvoice"``.
            **params: Query/body parameters forwarded to the API.

        Returns:
            The ``result`` value from the API response (dict or list).

        Raises:
            RuntimeError: If the API returns ``ok=False``.
        """
        url = f"{self._base_url}/{endpoint}"
        session = self._get_session()
        if method == "GET":
            async with session.get(url, params=params) as resp:
                data: dict[str, Any] = await resp.json()
        else:
            # Filter out None values so the API doesn't receive nulls
            body = {k: v for k, v in params.items() if v is not None}
            async with session.post(url, json=body) as resp:
                data = await resp.json()

        if not data.get("ok"):
            error = data.get("error", {})
            raise RuntimeError(
                f"Crypto Pay API error on {endpoint}: "
                f"code={error.get('code')}, name={error.get('name')}"
            )
        return data["result"]

    # ── Invoice ────────────────────────────────────────────────────────────────

    async def create_invoice(
        self,
        asset: str,
        amount: float,
        payload: str,
    ) -> dict[str, Any]:
        """Create a Crypto Pay invoice.

        Args:
            asset: Crypto asset ticker, e.g. ``"USDT"``. Must be in SUPPORTED_ASSETS.
            amount: Amount of crypto to request. Must be positive.
            payload: Arbitrary string stored in the invoice
                     (use the order UUID so the webhook can correlate it).

        Returns:
            Dict containing ``invoice_id``, ``pay_url``, and ``status``.

        Raises:
            ValueError: If *asset* is not supported or *amount* is non-positive.
            RuntimeError: If the Crypto Pay API returns an error.
        """
        if asset not in SUPPORTED_ASSETS:
            raise ValueError(f"Unsupported asset: {asset!r}. Allowed: {SUPPORTED_ASSETS}")
        if amount <= 0:
            raise ValueError(f"Amount must be positive, got {amount}")

        result: dict[str, Any] = await self._request(
            "POST",
            "createInvoice",
            asset=asset,
            amount=str(amount),
            payload=payload,
            expires_in=1800,  # 30 minutes — matches ORDER_TIMEOUT_SEC
        )
        log.info(
            "cryptopay_invoice_created",
            asset=asset,
            amount=amount,
            invoice_id=result.get("invoice_id"),
            status="ok",
        )
        return {
            "invoice_id": str(result["invoice_id"]),
            "pay_url": result["bot_invoice_url"],
            "status": result["status"],
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
            amount: Amount to transfer. Must be positive.
            spend_id: Unique string per transfer (use order UUID).

        Returns:
            Dict with ``transfer_id``, ``spend_id``, and ``status``.

        Raises:
            ValueError: If *asset* is not supported or *amount* is non-positive.
            RuntimeError: If the Crypto Pay API returns an error.
        """
        if asset not in SUPPORTED_ASSETS:
            raise ValueError(f"Unsupported asset: {asset!r}")
        if amount <= 0:
            raise ValueError(f"Transfer amount must be positive, got {amount}")

        result: dict[str, Any] = await self._request(
            "POST",
            "transfer",
            user_id=user_id,
            asset=asset,
            amount=str(amount),
            spend_id=spend_id,
        )
        log.info(
            "cryptopay_transfer_sent",
            user_id=user_id,
            asset=asset,
            amount=amount,
            spend_id=spend_id,
            transfer_id=result.get("transfer_id"),
            status="ok",
        )
        return {
            "transfer_id": result.get("transfer_id"),
            "spend_id": spend_id,
            "status": result.get("status", "unknown"),
        }

    # ── Exchange rates ─────────────────────────────────────────────────────────

    async def get_exchange_rates(self) -> list[dict[str, Any]]:
        """Fetch current exchange rates from Crypto Pay.

        Returns:
            List of rate dicts: ``[{"source": "USDT", "target": "USD", "rate": "1.0"}, ...]``.

        Raises:
            RuntimeError: If the Crypto Pay API returns an error.
        """
        result: Any = await self._request("GET", "getExchangeRates")
        rates_list: list[dict[str, Any]] = result if isinstance(result, list) else []
        return [
            {
                "source": r["source"],
                "target": r["target"],
                "rate": r["rate"],
            }
            for r in rates_list
        ]

    # ── Webhook signature verification ─────────────────────────────────────────

    def verify_webhook_signature(self, body: bytes, signature: str) -> bool:
        """Verify the HMAC-SHA256 signature of an incoming Crypto Pay webhook.

        Compares in constant time (``hmac.compare_digest``) to prevent
        timing-attack exposure.

        Args:
            body: Raw request body bytes.
            signature: Value of the ``crypto-pay-api-signature`` header.

        Returns:
            ``True`` if the signature is valid, ``False`` otherwise.
        """
        secret_key = hashlib.sha256(self._callback_secret.encode()).digest()
        expected = _hmac.new(secret_key, body, hashlib.sha256).hexdigest()
        valid = _hmac.compare_digest(expected, signature.lower())
        if not valid:
            log.warning("webhook_hmac_failed", status="invalid_signature")
        return valid

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    async def close(self) -> None:
        """Close the underlying aiohttp session gracefully."""
        if self._session is not None and not self._session.closed:
            await self._session.close()
