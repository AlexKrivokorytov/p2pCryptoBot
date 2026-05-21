import asyncio
import logging
from decimal import Decimal

import aiohttp

log = logging.getLogger(__name__)


class FiatRateProvider:
    """Fetches fiat exchange rates for CIS/local currencies not on Binance."""

    BASE_URL = "https://v6.exchangerate-api.com/v6"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    async def get_rate_to_usdt(self, fiat_currency: str) -> Decimal:
        """Return how many units of fiat_currency equal 1 USDT.

        Since USD is roughly 1:1 with USDT, we fetch USD to fiat_currency.
        Args:
            fiat_currency: ISO 4217 code, e.g. "RUB", "UAH", "KZT".
        Returns:
            Exchange rate as Decimal.
        Raises:
            RuntimeError: If API call fails.
        """
        if not self._api_key:
            # Fallback for dev environment without API key
            fallbacks = {"RUB": "100.0", "UAH": "40.0", "KZT": "450.0", "TRY": "30.0", "BYN": "3.3"}
            if fiat_currency in fallbacks:
                return Decimal(fallbacks[fiat_currency])
            return Decimal("1.0")

        url = f"{self.BASE_URL}/{self._api_key}/latest/USD"
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, timeout=5) as response:
                    if response.status != 200:
                        body = await response.text()
                        log.error(
                            "fiat_rate_fetch_failed",
                            status=response.status,
                            body=body,
                            step="get_rate_to_usdt",
                        )
                        raise RuntimeError(f"Rate fetch failed with status {response.status}")
                    
                    data = await response.json()
                    rates = data.get("conversion_rates", {})
                    if fiat_currency not in rates:
                        raise RuntimeError(f"Currency {fiat_currency} not found in rates")
                    
                    return Decimal(str(rates[fiat_currency]))
            except Exception as e:
                log.error("fiat_rate_fetch_error", error=str(e), step="get_rate_to_usdt")
                raise RuntimeError(f"Failed to fetch fiat rate: {e}") from e
