"""Unit tests for providers/fiat_rate_provider.py."""

import json
from decimal import Decimal
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from providers.fiat_rate_provider import FiatRateProvider

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_fiat_rate_provider_no_api_key():
    """Test fallback logic when API key is missing."""
    provider = FiatRateProvider(api_key="")
    
    assert await provider.get_rate_to_usdt("RUB") == Decimal("100.0")
    assert await provider.get_rate_to_usdt("UAH") == Decimal("40.0")
    assert await provider.get_rate_to_usdt("KZT") == Decimal("450.0")
    assert await provider.get_rate_to_usdt("TRY") == Decimal("30.0")
    assert await provider.get_rate_to_usdt("BYN") == Decimal("3.3")
    assert await provider.get_rate_to_usdt("UNKNOWN") == Decimal("1.0")


@pytest.mark.asyncio
async def test_fiat_rate_provider_success():
    """Test successful API call."""
    provider = FiatRateProvider(api_key="test_key")
    
    # Mock aiohttp ClientSession
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json.return_value = {"conversion_rates": {"RUB": 95.5}}
    
    mock_get_ctx = MagicMock()
    mock_get_ctx.__aenter__.return_value = mock_response
    mock_get_ctx.__aexit__.return_value = None
    
    mock_session = MagicMock()
    mock_session.get.return_value = mock_get_ctx
    
    mock_session_ctx = MagicMock()
    mock_session_ctx.__aenter__.return_value = mock_session
    mock_session_ctx.__aexit__.return_value = None

    with patch("providers.fiat_rate_provider.aiohttp.ClientSession", return_value=mock_session_ctx):
        rate = await provider.get_rate_to_usdt("RUB")
        
        assert rate == Decimal("95.5")


@pytest.mark.asyncio
async def test_fiat_rate_provider_api_error_status():
    """Test API call returning non-200 status."""
    provider = FiatRateProvider(api_key="test_key")
    
    mock_response = AsyncMock()
    mock_response.status = 500
    mock_response.text.return_value = "Internal Server Error"
    
    mock_get_ctx = MagicMock()
    mock_get_ctx.__aenter__.return_value = mock_response
    mock_get_ctx.__aexit__.return_value = None
    
    mock_session = MagicMock()
    mock_session.get.return_value = mock_get_ctx
    
    mock_session_ctx = MagicMock()
    mock_session_ctx.__aenter__.return_value = mock_session
    mock_session_ctx.__aexit__.return_value = None

    with (
        patch("providers.fiat_rate_provider.aiohttp.ClientSession", return_value=mock_session_ctx),
        pytest.raises(RuntimeError, match="Rate fetch failed with status 500"),
    ):
        await provider.get_rate_to_usdt("RUB")


@pytest.mark.asyncio
async def test_fiat_rate_provider_currency_not_found():
    """Test API call when currency is not in conversion_rates."""
    provider = FiatRateProvider(api_key="test_key")
    
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json.return_value = {"conversion_rates": {"EUR": 0.9}}
    
    mock_get_ctx = MagicMock()
    mock_get_ctx.__aenter__.return_value = mock_response
    mock_get_ctx.__aexit__.return_value = None
    
    mock_session = MagicMock()
    mock_session.get.return_value = mock_get_ctx
    
    mock_session_ctx = MagicMock()
    mock_session_ctx.__aenter__.return_value = mock_session
    mock_session_ctx.__aexit__.return_value = None

    with (
        patch("providers.fiat_rate_provider.aiohttp.ClientSession", return_value=mock_session_ctx),
        pytest.raises(RuntimeError, match="Currency RUB not found in rates"),
    ):
        await provider.get_rate_to_usdt("RUB")


@pytest.mark.asyncio
async def test_fiat_rate_provider_exception():
    """Test exception during API call."""
    provider = FiatRateProvider(api_key="test_key")
    
    mock_get_ctx = MagicMock()
    mock_get_ctx.__aenter__.side_effect = Exception("Network error")
    mock_get_ctx.__aexit__.return_value = None
    
    mock_session = MagicMock()
    mock_session.get.return_value = mock_get_ctx
    
    mock_session_ctx = MagicMock()
    mock_session_ctx.__aenter__.return_value = mock_session
    mock_session_ctx.__aexit__.return_value = None

    with (
        patch("providers.fiat_rate_provider.aiohttp.ClientSession", return_value=mock_session_ctx),
        pytest.raises(RuntimeError, match="Failed to fetch fiat rate: Network error"),
    ):
        await provider.get_rate_to_usdt("RUB")
