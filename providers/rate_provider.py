"""Binance Public Rate Provider.

Fetches real-time market prices from Binance without authentication.
Used only for *informational* rate hints — never for financial settlement.

Public endpoints used:
- ``GET /api/v3/ticker/price`` — latest spot price for SYMBOL/USDT
- ``GET /api/v3/exchangeInfo`` — not needed (we know symbols)

Rate limits: Binance public API allows 1200 weight/min. Each price call = 1 weight.
We use a TTL cache (30s) to stay well within limits.
"""

from __future__ import annotations

import time
from decimal import Decimal, InvalidOperation
from typing import Any

import aiohttp
import structlog

log = structlog.get_logger(__name__)

# Base URL for Binance Spot API (no auth required)
_BINANCE_BASE = "https://api.binance.com"

# Cache TTL in seconds
_CACHE_TTL = 30

# In-memory cache: {symbol: (price, timestamp)}
_price_cache: dict[str, tuple[Decimal, float]] = {}

# Assets supported by the rate provider
# Keys are SupportedAsset values; values are Binance pair suffixes
_ASSET_TO_BINANCE_SYMBOL: dict[str, str] = {
    "BTC": "BTCUSDT",
    "ETH": "ETHUSDT",
    "TON": "TONUSDT",
    "USDT": None,  # USDT is the quote currency — always 1.0
    "USDC": "USDCUSDT",
    "BNB": "BNBUSDT",
}

# Supported fiat currencies mapped to USDT exchange rate sources.
# USD ≈ USDT (pegged), EUR/GBP etc. via Binance's cross pairs where available.
_FIAT_USDT_SYMBOLS: dict[str, str | None] = {
    "USD": None,  # USDT ≈ USD, rate = 1.0
    "USDT": None,  # identity
    "EUR": "EURUSDT",  # Binance has EUR/USDT
    "GBP": "GBPUSDT",  # Binance has GBP/USDT
    "RUB": None,  # Binance deprecated RUB pairs — use fallback
    "TRY": "USDTRY",  # Turkish Lira (inverted: USDT/TRY)
    "BRL": "USDTBRL",  # Brazilian Real (inverted)
    "UAH": None,  # Not available — use fallback
}

# Timeout for each Binance request
_REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=5)


def _is_cached(symbol: str) -> bool:
    """Return True if *symbol* has a fresh cache entry."""
    entry = _price_cache.get(symbol)
    if entry is None:
        return False
    _, ts = entry
    return (time.monotonic() - ts) < _CACHE_TTL


async def _fetch_binance_price(symbol: str) -> Decimal | None:
    """Fetch spot price for *symbol* from Binance, respecting the TTL cache.

    Args:
        symbol: Binance trading pair, e.g. ``"BTCUSDT"``.

    Returns:
        Price as :class:`~decimal.Decimal`, or ``None`` on failure.
    """
    if _is_cached(symbol):
        return _price_cache[symbol][0]

    try:
        url = f"{_BINANCE_BASE}/api/v3/ticker/price"
        async with (
            aiohttp.ClientSession(timeout=_REQUEST_TIMEOUT) as session,
            session.get(url, params={"symbol": symbol}) as resp,
        ):
            if resp.status != 200:
                log.warning(
                    "binance_http_error",
                    symbol=symbol,
                    status=resp.status,
                    step="_fetch_binance_price",
                )
                return None
            data: dict[str, Any] = await resp.json()

        price = Decimal(data["price"])
        _price_cache[symbol] = (price, time.monotonic())
        log.info(
            "binance_price_fetched",
            symbol=symbol,
            price=str(price),
            step="_fetch_binance_price",
        )
        return price

    except (aiohttp.ClientError, KeyError, InvalidOperation) as exc:
        log.warning(
            "binance_fetch_error",
            symbol=symbol,
            error=str(exc),
            step="_fetch_binance_price",
        )
        return None


async def get_crypto_usdt_price(asset: str) -> Decimal | None:
    """Return the current USDT price of *asset*.

    Args:
        asset: Crypto ticker, e.g. ``"BTC"``, ``"ETH"``, ``"TON"``.

    Returns:
        Price in USDT as :class:`~decimal.Decimal`, or ``None`` if unavailable.
    """
    asset_upper = asset.upper()

    if asset_upper in ("USDT", "USDC"):
        return Decimal("1")  # stablecoins ≈ 1 USDT

    symbol = _ASSET_TO_BINANCE_SYMBOL.get(asset_upper)
    if symbol is None:
        return None

    return await _fetch_binance_price(symbol)


async def get_usdt_fiat_rate(fiat: str) -> Decimal | None:
    """Return how many fiat units = 1 USDT.

    For USD: returns 1.0 (pegged).
    For EUR/GBP: returns 1/EURUSDT (how many EUR per 1 USDT).
    For TRY/BRL: inverted pair (USDTRY = how many TRY per 1 USDT).
    For RUB/UAH: returns None (deprecated on Binance).

    Args:
        fiat: Fiat currency ticker, e.g. ``"USD"``, ``"EUR"``, ``"RUB"``.

    Returns:
        Rate as :class:`~decimal.Decimal`, or ``None`` if unavailable.
    """
    fiat_upper = fiat.upper()

    if fiat_upper in ("USD", "USDT"):
        return Decimal("1")

    symbol_info = _FIAT_USDT_SYMBOLS.get(fiat_upper)
    if symbol_info is None:
        return None  # not on Binance (RUB, UAH, etc.)

    raw = await _fetch_binance_price(symbol_info)
    if raw is None:
        return None

    # For pairs like EURUSDT: 1 EUR = X USDT → 1 USDT = 1/X EUR
    # For pairs like USDTRY: 1 USDT = X TRY → already correct
    if symbol_info.startswith("USD"):
        # Inverted pair: USDTTRY means 1 USDT = price TRY
        return raw
    else:
        # Normal pair: EURUSDT means 1 EUR = price USDT → 1 USDT = 1/price EUR
        return Decimal("1") / raw
