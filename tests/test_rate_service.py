"""Tests for rate_provider and rate_service (Binance integration).

All external HTTP calls are mocked — no real network requests during tests.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── rate_provider: get_crypto_usdt_price ─────────────────────────────────────

@pytest.mark.asyncio
@patch("providers.rate_provider._fetch_binance_price", new_callable=AsyncMock)
async def test_get_crypto_usdt_price_btc(mock_fetch: AsyncMock) -> None:
    """BTC price fetched via BTCUSDT symbol."""
    from providers.rate_provider import get_crypto_usdt_price

    mock_fetch.return_value = Decimal("65000.00")
    result = await get_crypto_usdt_price("BTC")

    mock_fetch.assert_called_once_with("BTCUSDT")
    assert result == Decimal("65000.00")


@pytest.mark.asyncio
@patch("providers.rate_provider._fetch_binance_price", new_callable=AsyncMock)
async def test_get_crypto_usdt_price_eth(mock_fetch: AsyncMock) -> None:
    """ETH price fetched via ETHUSDT symbol."""
    from providers.rate_provider import get_crypto_usdt_price

    mock_fetch.return_value = Decimal("3500.00")
    result = await get_crypto_usdt_price("ETH")

    mock_fetch.assert_called_once_with("ETHUSDT")
    assert result == Decimal("3500.00")


@pytest.mark.asyncio
async def test_get_crypto_usdt_price_usdt_stablecoin() -> None:
    """USDT always returns 1.0 without a network call."""
    from providers.rate_provider import get_crypto_usdt_price

    result = await get_crypto_usdt_price("USDT")
    assert result == Decimal("1")


@pytest.mark.asyncio
async def test_get_crypto_usdt_price_usdc_stablecoin() -> None:
    """USDC always returns 1.0 without a network call."""
    from providers.rate_provider import get_crypto_usdt_price

    result = await get_crypto_usdt_price("USDC")
    assert result == Decimal("1")


@pytest.mark.asyncio
@patch("providers.rate_provider._fetch_binance_price", new_callable=AsyncMock)
async def test_get_crypto_usdt_price_unknown_asset(mock_fetch: AsyncMock) -> None:
    """Unknown asset returns None without fetching."""
    from providers.rate_provider import get_crypto_usdt_price

    result = await get_crypto_usdt_price("DOGE123")

    mock_fetch.assert_not_called()
    assert result is None


# ── rate_provider: get_usdt_fiat_rate ────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_usdt_fiat_rate_usd() -> None:
    """USD returns 1.0 (pegged) without a network call."""
    from providers.rate_provider import get_usdt_fiat_rate

    result = await get_usdt_fiat_rate("USD")
    assert result == Decimal("1")


@pytest.mark.asyncio
@patch("providers.rate_provider._fetch_binance_price", new_callable=AsyncMock)
async def test_get_usdt_fiat_rate_eur(mock_fetch: AsyncMock) -> None:
    """EUR rate: 1 USDT = 1 / EURUSDT rate."""
    from providers.rate_provider import get_usdt_fiat_rate

    # EURUSDT = 1.08 means 1 EUR = 1.08 USDT → 1 USDT = 0.9259... EUR
    mock_fetch.return_value = Decimal("1.08")
    result = await get_usdt_fiat_rate("EUR")

    expected = Decimal("1") / Decimal("1.08")
    assert result is not None
    assert abs(result - expected) < Decimal("0.0001")


@pytest.mark.asyncio
@patch("providers.rate_provider._fetch_binance_price", new_callable=AsyncMock)
async def test_get_usdt_fiat_rate_try_inverted(mock_fetch: AsyncMock) -> None:
    """TRY rate: USDTRY pair is 'how many TRY per 1 USDT' — already correct."""
    from providers.rate_provider import get_usdt_fiat_rate

    mock_fetch.return_value = Decimal("32.50")
    result = await get_usdt_fiat_rate("TRY")

    assert result == Decimal("32.50")


@pytest.mark.asyncio
async def test_get_usdt_fiat_rate_rub_unavailable() -> None:
    """RUB returns None (deprecated on Binance)."""
    from providers.rate_provider import get_usdt_fiat_rate

    result = await get_usdt_fiat_rate("RUB")
    assert result is None


@pytest.mark.asyncio
async def test_get_usdt_fiat_rate_unknown_fiat() -> None:
    """Unknown fiat returns None."""
    from providers.rate_provider import get_usdt_fiat_rate

    result = await get_usdt_fiat_rate("XYZ")
    assert result is None


# ── rate_provider: TTL cache ─────────────────────────────────────────────────

@pytest.mark.asyncio
@patch("providers.rate_provider.aiohttp.ClientSession")
async def test_price_cache_hit(mock_session_cls: MagicMock) -> None:
    """Second call within TTL does NOT make a new HTTP request."""
    import time
    from providers import rate_provider

    # Pre-populate cache with a fresh entry
    rate_provider._price_cache["BTCUSDT"] = (Decimal("50000"), time.monotonic())

    result = await rate_provider._fetch_binance_price("BTCUSDT")

    # No HTTP call should be made
    mock_session_cls.assert_not_called()
    assert result == Decimal("50000")

    # Cleanup
    del rate_provider._price_cache["BTCUSDT"]


# ── rate_service: get_market_rate ────────────────────────────────────────────

@pytest.mark.asyncio
@patch("services.rate_service.get_usdt_fiat_rate", new_callable=AsyncMock)
@patch("services.rate_service.get_crypto_usdt_price", new_callable=AsyncMock)
async def test_get_market_rate_btc_usd(
    mock_crypto: AsyncMock, mock_fiat: AsyncMock
) -> None:
    """BTC/USD rate = BTCUSDT * 1.0."""
    from services.rate_service import get_market_rate

    mock_crypto.return_value = Decimal("65000")
    mock_fiat.return_value = Decimal("1")

    result = await get_market_rate("BTC", "USD")
    assert result == Decimal("65000")


@pytest.mark.asyncio
@patch("services.rate_service.get_usdt_fiat_rate", new_callable=AsyncMock)
@patch("services.rate_service.get_crypto_usdt_price", new_callable=AsyncMock)
async def test_get_market_rate_btc_eur(
    mock_crypto: AsyncMock, mock_fiat: AsyncMock
) -> None:
    """BTC/EUR rate = BTCUSDT * (1/EURUSDT)."""
    from services.rate_service import get_market_rate

    mock_crypto.return_value = Decimal("65000")
    mock_fiat.return_value = Decimal("1") / Decimal("1.08")  # ≈ 0.9259

    result = await get_market_rate("BTC", "EUR")
    assert result is not None
    # 65000 * 0.9259 ≈ 60185
    assert 59000 < result < 62000


@pytest.mark.asyncio
@patch("services.rate_service.get_usdt_fiat_rate", new_callable=AsyncMock)
@patch("services.rate_service.get_crypto_usdt_price", new_callable=AsyncMock)
async def test_get_market_rate_unavailable_fiat(
    mock_crypto: AsyncMock, mock_fiat: AsyncMock
) -> None:
    """Returns None when fiat rate is unavailable (e.g. RUB)."""
    from services.rate_service import get_market_rate

    mock_crypto.return_value = Decimal("65000")
    mock_fiat.return_value = None

    result = await get_market_rate("BTC", "RUB")
    assert result is None


@pytest.mark.asyncio
@patch("services.rate_service.get_usdt_fiat_rate", new_callable=AsyncMock)
@patch("services.rate_service.get_crypto_usdt_price", new_callable=AsyncMock)
async def test_get_market_rate_unavailable_asset(
    mock_crypto: AsyncMock, mock_fiat: AsyncMock
) -> None:
    """Returns None when asset price is unavailable."""
    from services.rate_service import get_market_rate

    mock_crypto.return_value = None
    mock_fiat.return_value = Decimal("1")

    result = await get_market_rate("UNKNOWN", "USD")
    assert result is None


@pytest.mark.asyncio
@patch("services.rate_service.get_usdt_fiat_rate", new_callable=AsyncMock)
@patch("services.rate_service.get_crypto_usdt_price", new_callable=AsyncMock)
async def test_get_market_rate_timeout(
    mock_crypto: AsyncMock, mock_fiat: AsyncMock
) -> None:
    """Timeout returns None without raising."""
    import asyncio
    from services.rate_service import get_market_rate

    async def slow(*args: object, **kwargs: object) -> Decimal:
        await asyncio.sleep(100)
        return Decimal("1")

    mock_crypto.side_effect = slow
    mock_fiat.side_effect = slow

    import services.rate_service as rs
    original = rs._RATE_TIMEOUT
    rs._RATE_TIMEOUT = 0.01
    try:
        result = await get_market_rate("BTC", "USD")
    finally:
        rs._RATE_TIMEOUT = original

    assert result is None


# ── rate_service: format_rate_hint ───────────────────────────────────────────

def test_format_rate_hint_large_number() -> None:
    """Large rates are formatted with thousands separator."""
    from services.rate_service import format_rate_hint

    text = format_rate_hint("BTC", "USD", Decimal("65000"))
    assert "65,000.00" in text
    assert "BTC" in text
    assert "USD" in text
    assert "Binance" in text


def test_format_rate_hint_small_rate() -> None:
    """Rates < 1 are formatted with 6 decimal places."""
    from services.rate_service import format_rate_hint

    text = format_rate_hint("USDT", "EUR", Decimal("0.925926"))
    assert "0.925926" in text


# ── rate_service: get_rate_hint_text ─────────────────────────────────────────

@pytest.mark.asyncio
@patch("services.rate_service.get_market_rate", new_callable=AsyncMock)
async def test_get_rate_hint_text_with_rate(mock_rate: AsyncMock) -> None:
    """Returns formatted hint when rate is available."""
    from services.rate_service import get_rate_hint_text

    mock_rate.return_value = Decimal("65000")
    result = await get_rate_hint_text("BTC", "USD")

    assert "65,000.00" in result
    assert "Binance" in result


@pytest.mark.asyncio
@patch("services.rate_service.get_market_rate", new_callable=AsyncMock)
async def test_get_rate_hint_text_no_rate(mock_rate: AsyncMock) -> None:
    """Returns empty string when rate is unavailable."""
    from services.rate_service import get_rate_hint_text

    mock_rate.return_value = None
    result = await get_rate_hint_text("BTC", "RUB")

    assert result == ""
