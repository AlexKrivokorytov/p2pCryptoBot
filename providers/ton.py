"""TON Blockchain provider using pytoniq LiteClient."""

from __future__ import annotations

from typing import Any

import structlog

log = structlog.get_logger(__name__)


class TONProvider:
    """Provider for interacting with the TON blockchain."""

    def __init__(self, is_testnet: bool = False):
        self.is_testnet = is_testnet
        self._client: Any = None

    async def _get_client(self) -> Any:
        """Lazy initialization of LiteClient."""
        if self._client is None:
            # Local import as per Project Rule 5
            from pytoniq import LiteClient  # type: ignore[attr-defined]

            if self.is_testnet:
                self._client = await LiteClient.from_testnet_config(trust_level=2)
            else:
                self._client = await LiteClient.from_mainnet_config(trust_level=2)
        return self._client

    async def connect(self) -> None:
        """Connect to TON network."""
        client = await self._get_client()
        await client.connect()
        log.info("ton_provider_connected", testnet=self.is_testnet)

    async def disconnect(self) -> None:
        """Close TON connection."""
        if self._client:
            await self._client.close()
            self._client = None
            log.info("ton_provider_disconnected")

    async def get_transactions(self, address: str, limit: int = 20) -> list[dict[str, Any]]:
        """Fetch recent transactions for a given TON address.

        Args:
            address: TON address to scan.
            limit: Number of transactions to fetch.

        Returns:
            List of transaction details with hash, amount, and memo.
        """
        client = await self._get_client()
        txs = await client.get_transactions(address, count=limit)

        results = []
        for tx in txs:
            # pytoniq Transaction object parsing
            # Amount is in nanotons
            in_msg = tx.in_msg
            if not in_msg or not in_msg.info or in_msg.info.type != "int_msg":
                continue

            # Extract memo (comment)
            memo = ""
            if in_msg.body:
                try:
                    # Simple comment body is often a Cell with 32-bit zero prefix
                    # We try to parse it as a string
                    cell = in_msg.body
                    slice_ = cell.begin_parse()
                    if len(slice_) >= 32:
                        prefix = slice_.load_uint(32)
                        if prefix == 0:
                            memo = slice_.load_snake_string()
                except Exception:
                    pass

            results.append(
                {
                    "hash": tx.hash.hex(),
                    "amount_nanotons": int(in_msg.info.value),
                    "memo": memo,
                    "utime": tx.utime,
                }
            )

        return results
