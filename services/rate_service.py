"""Rate service — market rate hints for P2P ad creation.

Provides suggested prices based on Binance spot data.
All results are advisory only — never used for financial settlement.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal

import structlog

from providers.rate_provider import get_crypto_usdt_price, get_usdt_fiat_rate

log = structlog.get_logger(__name__)

# Timeout for rate lookups (both legs of the calculation)
_RATE_TIMEOUT = 5


async def get_market_rate(asset: str, fiat: str) -> Decimal | None:
    """Return the current market rate: how many *fiat* units = 1 *asset*.

    Calculation:
        rate = (1 asset in USDT) * (USDT in fiat)

    Examples:
        - BTC/USD: BTCUSDT price * 1.0 = ~65000
        - BTC/EUR: BTCUSDT price * (1/EURUSDT) = ~60000
        - TON/RUB: TONUSDT * None = None (RUB not on Binance)
        - USDT/USD: 1 * 1 = 1.0

    Args:
        asset: Crypto ticker, e.g. ``"BTC"``, ``"TON"``, ``"USDT"``.
        fiat:  Fiat currency code, e.g. ``"USD"``, ``"EUR"``, ``"RUB"``.

    Returns:
        Rate as :class:`~decimal.Decimal`, or ``None`` if either leg is unavailable.
    """
    try:
        crypto_price, fiat_rate = await asyncio.wait_for(
            asyncio.gather(
                get_crypto_usdt_price(asset),
                get_usdt_fiat_rate(fiat),
            ),
            timeout=_RATE_TIMEOUT,
        )
    except TimeoutError:
        log.warning(
            "rate_lookup_timeout",
            asset=asset,
            fiat=fiat,
            step="get_market_rate",
        )
        return None
    except Exception as exc:
        log.warning(
            "rate_lookup_error",
            asset=asset,
            fiat=fiat,
            error=str(exc),
            step="get_market_rate",
        )
        return None

    if crypto_price is None or fiat_rate is None:
        return None

    rate = crypto_price * fiat_rate
    log.info(
        "market_rate_calculated",
        asset=asset,
        fiat=fiat,
        rate=str(rate),
        step="get_market_rate",
    )
    return rate


def format_rate_hint(asset: str, fiat: str, rate: Decimal) -> str:
    """Format a user-friendly rate hint for the Telegram message.

    Args:
        asset: Crypto ticker, e.g. ``"BTC"``.
        fiat:  Fiat currency code, e.g. ``"USD"``.
        rate:  Market rate (how many fiat per 1 asset).

    Returns:
        Formatted HTML string, e.g.:
        ``📊 <b>Binance reference rate:</b> 1 BTC ≈ <code>65,000.00</code> USD``
    """
    # Format with commas, 2 decimal places for fiat display
    # Small rates (e.g. USDT/USD ≈ 1.0002) — show 6 decimals
    formatted = f"{rate:,.2f}" if rate >= 1 else f"{rate:.6f}"

    return (
        f"📊 <b>Binance reference rate:</b>\n"
        f"1 {asset} ≈ <code>{formatted}</code> {fiat}\n"
        f"<i>Source: Binance Spot (updated ~30s)</i>"
    )


async def get_rate_hint_text(asset: str, fiat: str) -> str:
    """Fetch the market rate and return a formatted hint, or empty string on failure.

    This is the entry point for handlers — never raises exceptions.

    Args:
        asset: Crypto ticker.
        fiat:  Fiat currency code.

    Returns:
        Formatted HTML rate hint, or ``""`` if rate is unavailable.
    """
    rate = await get_market_rate(asset, fiat)
    if rate is None:
        return ""
    return format_rate_hint(asset, fiat, rate)
