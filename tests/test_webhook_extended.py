"""Tests for webhook handler — full coverage of all response paths."""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.handlers.webhook import cryptopay_webhook
from db.models.order import Order, OrderStatus

# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_request(
    body: bytes,
    signature: str,
    crypto_pay: MagicMock,
    session_pool: MagicMock,
) -> MagicMock:
    """Build a fake aiohttp Request object."""
    request = MagicMock()
    request.headers = {"crypto-pay-api-signature": signature}
    request.read = AsyncMock(return_value=body)
    request.remote = "127.0.0.1"
    request.app = {"crypto_pay": crypto_pay, "session_pool": session_pool}
    return request


def _make_crypto_pay(valid_sig: bool = True) -> MagicMock:
    cp = MagicMock()
    cp.verify_webhook_signature = MagicMock(return_value=valid_sig)
    return cp


def _make_session_pool(order: Order | None) -> MagicMock:
    """Build a fake session_pool that returns the given order on query."""
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = order

    session.execute = AsyncMock(return_value=result)
    session.begin = MagicMock(
        return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=None), __aexit__=AsyncMock(return_value=False)
        )
    )

    pool = MagicMock()
    pool.return_value = AsyncMock(
        __aenter__=AsyncMock(return_value=session),
        __aexit__=AsyncMock(return_value=False),
    )
    return pool


# ── Signature failure ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_webhook_invalid_signature() -> None:
    """Returns 403 when HMAC signature is invalid."""
    crypto_pay = _make_crypto_pay(valid_sig=False)
    body = b'{"payload": {"status": "paid"}}'
    request = _make_request(body, "bad_sig", crypto_pay, MagicMock())

    response = await cryptopay_webhook(request)

    assert response.status == 403
    crypto_pay.verify_webhook_signature.assert_called_once_with(body, "bad_sig")


# ── Malformed payload ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_webhook_malformed_payload() -> None:
    """Returns 400 when JSON body is missing required keys."""
    crypto_pay = _make_crypto_pay(valid_sig=True)
    body = b'{"wrong_key": "value"}'
    request = _make_request(body, "sig", crypto_pay, MagicMock())

    response = await cryptopay_webhook(request)

    assert response.status == 400


@pytest.mark.asyncio
async def test_webhook_invalid_json() -> None:
    """Returns 400 when body is not valid JSON."""
    crypto_pay = _make_crypto_pay(valid_sig=True)
    body = b"NOT_JSON"
    request = _make_request(body, "sig", crypto_pay, MagicMock())

    response = await cryptopay_webhook(request)

    assert response.status == 400


# ── Paid → calls activate_order ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_webhook_paid_calls_activate_order() -> None:
    """Paid invoice triggers activate_order service call."""
    order_uuid = str(uuid.uuid4())
    crypto_pay = _make_crypto_pay(valid_sig=True)
    body = json.dumps(
        {"payload": {"status": "paid", "payload": order_uuid, "invoice_id": "inv_123"}}
    ).encode()

    session_pool = _make_session_pool(order=None)
    request = _make_request(body, "sig", crypto_pay, session_pool)

    with patch("bot.handlers.webhook.order_service") as mock_svc:
        mock_svc.activate_order = AsyncMock(
            return_value={"order_id": order_uuid, "status": OrderStatus.active}
        )
        response = await cryptopay_webhook(request)

    assert response.status == 200
    mock_svc.activate_order.assert_called_once()


@pytest.mark.asyncio
async def test_webhook_paid_activate_fails_gracefully() -> None:
    """Paid webhook still returns 200 even if activate_order raises ValueError."""
    order_uuid = str(uuid.uuid4())
    crypto_pay = _make_crypto_pay(valid_sig=True)
    body = json.dumps(
        {"payload": {"status": "paid", "payload": order_uuid, "invoice_id": "inv_999"}}
    ).encode()

    session_pool = _make_session_pool(order=None)
    request = _make_request(body, "sig", crypto_pay, session_pool)

    with patch("bot.handlers.webhook.order_service") as mock_svc:
        mock_svc.activate_order = AsyncMock(side_effect=ValueError("already active"))
        response = await cryptopay_webhook(request)

    assert response.status == 200


# ── Expired → cancelled ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_webhook_expired_transitions_to_cancelled() -> None:
    """Expired invoice on pending_funding order transitions to cancelled."""
    order = MagicMock()
    order.id = uuid.uuid4()
    order.status = OrderStatus.pending_funding
    order.maker_id = 456
    order.asset = "TON"
    order.amount = 50

    crypto_pay = _make_crypto_pay(valid_sig=True)
    body = json.dumps(
        {"payload": {"status": "expired", "payload": str(order.id), "invoice_id": "inv_456"}}
    ).encode()

    session_pool = _make_session_pool(order=order)
    request = _make_request(body, "sig", crypto_pay, session_pool)

    response = await cryptopay_webhook(request)

    assert response.status == 200
    assert order.status == OrderStatus.cancelled


# ── Already-processed (idempotency) ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_webhook_expired_but_already_active_noop() -> None:
    """Expired webhook on active order is a no-op (returns 200)."""
    order = MagicMock()
    order.id = uuid.uuid4()
    order.status = OrderStatus.active  # already activated
    order.maker_id = 789
    order.asset = "BTC"
    order.amount = 0.01

    crypto_pay = _make_crypto_pay(valid_sig=True)
    body = json.dumps(
        {"payload": {"status": "expired", "payload": str(order.id), "invoice_id": "inv_789"}}
    ).encode()

    session_pool = _make_session_pool(order=order)
    request = _make_request(body, "sig", crypto_pay, session_pool)

    response = await cryptopay_webhook(request)

    assert response.status == 200
    # Status must NOT change
    assert order.status == OrderStatus.active
