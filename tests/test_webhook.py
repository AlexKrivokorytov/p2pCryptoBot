"""Tests for Crypto Pay webhook handler."""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiohttp.test_utils import make_mocked_request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.handlers.webhook import cryptopay_webhook
from db.models.order import Order, OrderStatus, OrderType
from db.models.user import User


async def _create_order(session: AsyncSession, payload_uuid: str) -> Order:
    user = User(telegram_id=401, username="webhook_test")
    session.add(user)

    order = Order(
        maker_id=401,
        order_type=OrderType.sell_crypto,
        asset="USDC",
        amount=10.0,
        fiat_currency="USD",
        fiat_amount=10.0,
        payment_method="Sberbank",
        status=OrderStatus.pending_funding,
        crypto_pay_payload=payload_uuid,
        spend_id=str(uuid.uuid4()),
    )
    session.add(order)
    await session.flush()
    return order


def _mock_app(factory, crypto_pay_mock):
    return {
        "session_pool": factory,
        "crypto_pay": crypto_pay_mock,
    }


@pytest.mark.asyncio
async def test_webhook_hmac_failed() -> None:
    """Webhook rejects requests with invalid signature."""
    crypto_pay = MagicMock()
    crypto_pay.verify_webhook_signature.return_value = False

    request = make_mocked_request("POST", "/webhook/cryptopay", app=_mock_app(None, crypto_pay), headers={"crypto-pay-api-signature": "bad"})
    # Mock read() for body
    request.read = AsyncMock(return_value=b"{}")

    response = await cryptopay_webhook(request)
    assert response.status == 403
    assert response.text == "Invalid signature"


@pytest.mark.asyncio
async def test_webhook_malformed_payload() -> None:
    """Webhook rejects malformed JSON or missing fields."""
    crypto_pay = MagicMock()
    crypto_pay.verify_webhook_signature.return_value = True

    request = make_mocked_request("POST", "/webhook/cryptopay", app=_mock_app(None, crypto_pay))
    request.read = AsyncMock(return_value=b'{"bad": "json"}')

    response = await cryptopay_webhook(request)
    assert response.status == 400
    assert response.text == "Malformed payload"


@pytest.mark.asyncio
async def test_webhook_paid_success(engine) -> None:
    """Webhook activates order (pending_funding → active) when status=paid."""
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        async with session.begin():
            order = await _create_order(session, str(uuid.uuid4()))
            order_id = order.id
            payload_uuid = str(order_id)  # Use real UUID as payload

    # Update crypto_pay_payload to match the actual order id
    async with factory() as session:
        async with session.begin():
            db_order = await session.get(Order, order_id)
            db_order.crypto_pay_payload = payload_uuid

    crypto_pay = MagicMock()
    crypto_pay.verify_webhook_signature.return_value = True

    body = {
        "payload": {
            "status": "paid",
            "payload": payload_uuid,
            "invoice_id": 999
        }
    }

    request = make_mocked_request("POST", "/webhook/cryptopay", app=_mock_app(factory, crypto_pay))
    request.read = AsyncMock(return_value=json.dumps(body).encode())

    response = await cryptopay_webhook(request)
    assert response.status == 200

    # Verify db — order should now be active
    async with factory() as session:
        db_order = await session.get(Order, order_id)
        assert db_order.status == OrderStatus.active

        # Cleanup
        await session.delete(db_order)
        await session.commit()
