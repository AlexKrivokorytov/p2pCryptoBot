"""Abstract broker interface for exchange adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod


class BrokerBase(ABC):
    """Common interface for all exchange adapters (Binance, OKX, Bybit).

    Keys must have READ + TRADE permissions only — NO WITHDRAW.
    """

    @abstractmethod
    async def fetch_balance(self, asset: str) -> float:
        """Return the available balance for *asset* on this exchange.

        Args:
            asset: Ticker symbol, e.g. "USDT", "BTC".

        Returns:
            Available (free) balance as a float.
        """

    @abstractmethod
    async def create_order(
        self,
        asset: str,
        fiat_currency: str,
        side: str,
        amount: float,
    ) -> dict[str, object]:
        """Place a market/limit order on the exchange.

        Args:
            asset: Crypto asset ticker, e.g. "USDT".
            fiat_currency: Fiat pair, e.g. "RUB", "EUR".
            side: "buy" or "sell".
            amount: Crypto amount.

        Returns:
            Raw exchange order dict.
        """

    @abstractmethod
    async def close(self) -> None:
        """Cleanly close the underlying CCXT client."""
