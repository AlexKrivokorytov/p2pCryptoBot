"""Tests for providers/crypto_pay.py — _get_session and _request methods."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from providers.crypto_pay import CryptoPayClient


@pytest.fixture
def client() -> CryptoPayClient:
    """Return a fresh CryptoPayClient with fake environment variables."""
    with patch.dict(os.environ, {
        "CRYPTOPAY_TOKEN": "TEST_TOKEN",
        "CRYPTOPAY_CALLBACK_SECRET": "TEST_SECRET"
    }):
        return CryptoPayClient(testnet=True)


class TestGetSession:
    """Tests for the internal _get_session method."""

    def test_creates_session_on_first_call(self, client: CryptoPayClient) -> None:
        """_get_session should create and cache a new aiohttp session."""
        with patch("providers.crypto_pay.aiohttp.ClientSession") as mock_session_cls:
            mock_session = MagicMock()
            mock_session.closed = False
            mock_session_cls.return_value = mock_session

            session = client._get_session()

            mock_session_cls.assert_called_once()
            assert session is mock_session

    def test_reuses_existing_open_session(self, client: CryptoPayClient) -> None:
        """_get_session should return the same session if it's still open."""
        mock_session = MagicMock()
        mock_session.closed = False
        client._session = mock_session

        with patch("providers.crypto_pay.aiohttp.ClientSession") as mock_cls:
            result = client._get_session()
            mock_cls.assert_not_called()
            assert result is mock_session

    def test_recreates_session_if_closed(self, client: CryptoPayClient) -> None:
        """_get_session should create a new session if the old one is closed."""
        old_session = MagicMock()
        old_session.closed = True
        client._session = old_session

        with patch("providers.crypto_pay.aiohttp.ClientSession") as mock_cls:
            new_session = MagicMock()
            new_session.closed = False
            mock_cls.return_value = new_session

            result = client._get_session()

            mock_cls.assert_called_once()
            assert result is new_session


class TestRequest:
    """Tests for the internal _request method."""

    @pytest.mark.asyncio
    async def test_get_request_returns_result(self, client: CryptoPayClient) -> None:
        """_request with GET should return data['result'] on success."""
        mock_resp = AsyncMock()
        mock_resp.json = AsyncMock(return_value={"ok": True, "result": {"invoice_id": 42}})

        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_cm.__aexit__ = AsyncMock(return_value=None)

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_cm)

        with patch.object(client, "_get_session", return_value=mock_session):
            result = await client._request("GET", "getInvoices", invoice_id=42)

        assert result == {"invoice_id": 42}

    @pytest.mark.asyncio
    async def test_post_request_returns_result(self, client: CryptoPayClient) -> None:
        """_request with POST should send JSON body and return data['result']."""
        mock_resp = AsyncMock()
        mock_resp.json = AsyncMock(return_value={"ok": True, "result": {"status": "active"}})

        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_cm.__aexit__ = AsyncMock(return_value=None)

        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=mock_cm)

        with patch.object(client, "_get_session", return_value=mock_session):
            result = await client._request("POST", "createInvoice", asset="USDT", amount=10.0)

        assert result == {"status": "active"}

    @pytest.mark.asyncio
    async def test_request_raises_on_api_error(self, client: CryptoPayClient) -> None:
        """_request should raise RuntimeError if ok=False."""
        mock_resp = AsyncMock()
        mock_resp.json = AsyncMock(
            return_value={"ok": False, "error": {"code": 400, "name": "INVALID_PARAM"}}
        )

        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_cm.__aexit__ = AsyncMock(return_value=None)

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_cm)

        with patch.object(client, "_get_session", return_value=mock_session):
            with pytest.raises(RuntimeError, match="INVALID_PARAM"):
                await client._request("GET", "badEndpoint")

    @pytest.mark.asyncio
    async def test_post_filters_none_params(self, client: CryptoPayClient) -> None:
        """POST request body should not include keys with None values."""
        captured_body: dict = {}

        def fake_post(url: str, json: dict, **kwargs: Any) -> MagicMock:
            captured_body.update(json)
            mock_resp = AsyncMock()
            mock_resp.json = AsyncMock(return_value={"ok": True, "result": {}})
            cm = MagicMock()
            cm.__aenter__ = AsyncMock(return_value=mock_resp)
            cm.__aexit__ = AsyncMock(return_value=None)
            return cm

        mock_session = MagicMock()
        mock_session.post = fake_post

        with patch.object(client, "_get_session", return_value=mock_session):
            await client._request("POST", "createInvoice", asset="USDT", amount=10.0, comment=None)

        assert "comment" not in captured_body
        assert captured_body["asset"] == "USDT"
