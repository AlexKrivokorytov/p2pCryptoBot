"""Binance exchange adapter using CCXT async client.

Security: API keys must have READ + TRADE permissions only — no WITHDRAW.
"""

from __future__ import annotations

import os
import structlog
import ccxt.async_support as ccxt

from providers.broker.base import BrokerBase

log = structlog.get_logger(__name__)


class BinanceBroker(BrokerBase):
    """CCXT-based Binance adapter for spot balance and order placement."""

    def __init__(self) -> None:
        api_key = os.environ.get("BINANCE_API_KEY", "")
        api_secret = os.environ.get("BINANCE_API_SECRET", "")
        self._client = ccxt.binance(
            {
                "apiKey": api_key,
                "secret": api_secret,
                "enableRateLimit": True,
                "options": {"defaultType": "spot"},
            }
        )

    async def fetch_balance(self, asset: str) -> float:
        """Return free balance for *asset* on Binance spot.

        Args:
            asset: Ticker, e.g. "USDT".

        Returns:
            Free balance as float, or 0.0 if asset not found.
        """
        balance = await self._client.fetch_balance()
        free: float = balance.get("free", {}).get(asset, 0.0)
        log.info("binance_fetch_balance", asset=asset, free=free)
        return float(free)

    async def create_order(
        self,
        asset: str,
        fiat_currency: str,
        side: str,
        amount: float,
    ) -> dict[str, object]:
        """Place a market order on Binance.

        Args:
            asset: Crypto ticker, e.g. "USDT".
            fiat_currency: Fiat currency code, e.g. "RUB".
            side: "buy" or "sell".
            amount: Crypto amount.

        Returns:
            Raw CCXT order dict.
        """
        symbol = f"{asset}/{fiat_currency}"
        order = await self._client.create_market_order(symbol, side, amount)
        log.info(
            "binance_create_order",
            symbol=symbol,
            side=side,
            amount=amount,
            order_id=order.get("id"),
        )
        return dict(order)  # type: ignore[arg-type]

    async def close(self) -> None:
        """Close the CCXT async session."""
        await self._client.close()
