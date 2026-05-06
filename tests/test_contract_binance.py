"""
Contract tests — verify rate_provider against Binance Spot API response shapes.

External reference: https://binance-docs.github.io/apidocs/spot/en/#symbol-price-ticker
These tests verify we correctly parse the response format documented by Binance.
If Binance changes their API, these tests will catch regressions before production.
"""

from __future__ import annotations

import time
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Canonical Binance API response shapes ─────────────────────────────────────
# Source: https://binance-docs.github.io/apidocs/spot/en/#symbol-price-ticker

CANONICAL_TICKER_RESPONSE: dict[str, str] = {
    "symbol": "BTCUSDT",
    "price": "65432.10000000",
}
CANONICAL_MULTI_TICKER: list[dict[str, str]] = [
    {"symbol": "BTCUSDT", "price": "65432.10000000"},
    {"symbol": "ETHUSDT", "price": "3456.78000000"},
    {"symbol": "TONUSDT", "price": "5.23000000"},
]
CANONICAL_ERROR_RESPONSE: dict[str, object] = {"code": -1121, "msg": "Invalid symbol."}


def _make_mock_session(status: int, json_data: object) -> MagicMock:
    """Build a fully-mocked aiohttp.ClientSession returning the given response."""
    mock_resp = AsyncMock()
    mock_resp.status = status
    mock_resp.json = AsyncMock(return_value=json_data)

    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    mock_session = MagicMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.get.return_value = mock_ctx
    return mock_session


class TestBinancePriceResponseParsing:
    """Verify _fetch_binance_price correctly parses Binance's response format."""

    @pytest.mark.asyncio
    async def test_parses_price_field_as_decimal(self) -> None:
        """Price must be returned as Decimal, not float — to prevent precision loss."""
        from providers import rate_provider

        rate_provider._price_cache.pop("BTCUSDT", None)
        with patch(
            "providers.rate_provider.aiohttp.ClientSession",
            return_value=_make_mock_session(200, CANONICAL_TICKER_RESPONSE),
        ):
            result = await rate_provider._fetch_binance_price("BTCUSDT")

        assert result == Decimal("65432.10000000")
        assert isinstance(result, Decimal)

    @pytest.mark.asyncio
    async def test_handles_full_precision_price(self) -> None:
        """Binance returns 8 decimal places — precision must not be lost."""
        from providers import rate_provider

        rate_provider._price_cache.pop("ETHUSDT", None)
        data = {"symbol": "ETHUSDT", "price": "3456.78901234"}
        with patch(
            "providers.rate_provider.aiohttp.ClientSession",
            return_value=_make_mock_session(200, data),
        ):
            result = await rate_provider._fetch_binance_price("ETHUSDT")

        assert result == Decimal("3456.78901234")

    @pytest.mark.asyncio
    async def test_caches_result_for_ttl(self) -> None:
        """Second call within TTL must not make an HTTP request."""
        from providers import rate_provider

        rate_provider._price_cache["TONUSDT"] = (Decimal("5.23"), time.monotonic())
        with patch("providers.rate_provider.aiohttp.ClientSession") as mock_cls:
            result = await rate_provider._fetch_binance_price("TONUSDT")
            mock_cls.assert_not_called()

        assert result == Decimal("5.23")
        rate_provider._price_cache.pop("TONUSDT", None)

    @pytest.mark.asyncio
    async def test_cache_expires_after_ttl(self) -> None:
        """After TTL expires, a fresh HTTP request must be made."""
        from providers import rate_provider

        # Plant an expired cache entry (timestamp = now - 999 seconds)
        rate_provider._price_cache["BTCUSDT"] = (Decimal("1.0"), time.monotonic() - 999)
        with patch(
            "providers.rate_provider.aiohttp.ClientSession",
            return_value=_make_mock_session(200, CANONICAL_TICKER_RESPONSE),
        ):
            result = await rate_provider._fetch_binance_price("BTCUSDT")

        # Should have fetched fresh price, not the stale "1.0"
        assert result == Decimal("65432.10000000")
        rate_provider._price_cache.pop("BTCUSDT", None)

    @pytest.mark.asyncio
    async def test_returns_none_on_400_error(self) -> None:
        """Non-200 HTTP status must result in None, not an exception."""
        from providers import rate_provider

        rate_provider._price_cache.pop("INVALID", None)
        with patch(
            "providers.rate_provider.aiohttp.ClientSession",
            return_value=_make_mock_session(400, CANONICAL_ERROR_RESPONSE),
        ):
            result = await rate_provider._fetch_binance_price("INVALID")

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_404_error(self) -> None:
        """404 responses (symbol not found) must return None gracefully."""
        from providers import rate_provider

        rate_provider._price_cache.pop("XXXUSDT", None)
        with patch(
            "providers.rate_provider.aiohttp.ClientSession",
            return_value=_make_mock_session(404, {"code": -1121, "msg": "Invalid symbol."}),
        ):
            result = await rate_provider._fetch_binance_price("XXXUSDT")

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_network_error(self) -> None:
        """Network errors must result in None, not a crash."""
        import aiohttp as _aiohttp

        from providers import rate_provider

        rate_provider._price_cache.pop("BTCUSDT", None)
        with patch(
            "providers.rate_provider.aiohttp.ClientSession",
            side_effect=_aiohttp.ClientError("Connection refused"),
        ):
            result = await rate_provider._fetch_binance_price("BTCUSDT")

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_missing_price_key(self) -> None:
        """If API response is missing 'price' key, must return None gracefully."""
        from providers import rate_provider

        rate_provider._price_cache.pop("BTCUSDT", None)
        bad_response = {"symbol": "BTCUSDT"}  # missing "price"
        with patch(
            "providers.rate_provider.aiohttp.ClientSession",
            return_value=_make_mock_session(200, bad_response),
        ):
            result = await rate_provider._fetch_binance_price("BTCUSDT")

        assert result is None


class TestAssetToSymbolMapping:
    """Verify every supported asset maps to the correct Binance trading symbol."""

    @pytest.mark.parametrize(
        "asset,expected_symbol",
        [
            ("BTC", "BTCUSDT"),
            ("ETH", "ETHUSDT"),
            ("TON", "TONUSDT"),
            ("BNB", "BNBUSDT"),
            ("USDC", "USDCUSDT"),
        ],
    )
    def test_asset_maps_to_binance_symbol(self, asset: str, expected_symbol: str) -> None:
        """Each supported crypto must map to its correct Binance quote symbol."""
        from providers.rate_provider import _ASSET_TO_BINANCE_SYMBOL

        assert _ASSET_TO_BINANCE_SYMBOL[asset] == expected_symbol

    def test_usdt_has_no_symbol(self) -> None:
        """USDT is the quote currency — it must have None (no Binance symbol needed)."""
        from providers.rate_provider import _ASSET_TO_BINANCE_SYMBOL

        assert _ASSET_TO_BINANCE_SYMBOL["USDT"] is None

    @pytest.mark.asyncio
    async def test_usdt_returns_one_without_api_call(self) -> None:
        """USDT price must return Decimal('1') without making any HTTP call."""
        from providers.rate_provider import get_crypto_usdt_price

        with patch("providers.rate_provider.aiohttp.ClientSession") as mock_cls:
            result = await get_crypto_usdt_price("USDT")
            mock_cls.assert_not_called()
        assert result == Decimal("1")

    @pytest.mark.asyncio
    async def test_usdc_returns_one_without_api_call(self) -> None:
        """USDC (stablecoin) must return Decimal('1') without making any HTTP call."""
        from providers.rate_provider import get_crypto_usdt_price

        with patch("providers.rate_provider.aiohttp.ClientSession") as mock_cls:
            result = await get_crypto_usdt_price("USDC")
            mock_cls.assert_not_called()
        assert result == Decimal("1")

    @pytest.mark.asyncio
    async def test_unknown_asset_returns_none(self) -> None:
        """An unrecognised asset ticker must return None without calling Binance."""
        from providers.rate_provider import get_crypto_usdt_price

        with patch("providers.rate_provider.aiohttp.ClientSession") as mock_cls:
            result = await get_crypto_usdt_price("SHIB")
            mock_cls.assert_not_called()
        assert result is None


class TestFiatRateContract:
    """Verify get_usdt_fiat_rate returns correct rate for each supported fiat."""

    @pytest.mark.asyncio
    async def test_usd_returns_one_no_api_call(self) -> None:
        """USD ≈ USDT — must return Decimal('1') without any network call."""
        from providers.rate_provider import get_usdt_fiat_rate

        with patch("providers.rate_provider.aiohttp.ClientSession") as mock_cls:
            result = await get_usdt_fiat_rate("USD")
            mock_cls.assert_not_called()
        assert result == Decimal("1")

    @pytest.mark.asyncio
    async def test_eur_rate_is_inverted(self) -> None:
        """EUR rate = 1 / EURUSDT. If EURUSDT=1.1 then 1 USDT = 0.909... EUR."""
        from providers import rate_provider

        rate_provider._price_cache.pop("EURUSDT", None)
        data = {"symbol": "EURUSDT", "price": "1.1000"}
        with patch(
            "providers.rate_provider.aiohttp.ClientSession",
            return_value=_make_mock_session(200, data),
        ):
            result = await rate_provider.get_usdt_fiat_rate("EUR")

        assert result is not None
        assert abs(result - Decimal("1") / Decimal("1.1000")) < Decimal("0.000001")
        rate_provider._price_cache.pop("EURUSDT", None)

    @pytest.mark.asyncio
    async def test_rub_returns_none(self) -> None:
        """RUB is deprecated on Binance — must return None without crashing."""
        from providers.rate_provider import get_usdt_fiat_rate

        with patch("providers.rate_provider.aiohttp.ClientSession") as mock_cls:
            result = await get_usdt_fiat_rate("RUB")
            mock_cls.assert_not_called()
        assert result is None

    @pytest.mark.asyncio
    async def test_unknown_fiat_returns_none(self) -> None:
        """An unrecognised fiat ticker must return None."""
        from providers.rate_provider import get_usdt_fiat_rate

        result = await get_usdt_fiat_rate("XYZ")
        assert result is None
