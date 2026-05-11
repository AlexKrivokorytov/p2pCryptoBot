"""Final coverage push for 98%+."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from db.models.order import OrderStatus, OrderType
from providers.ton import TONProvider
from services import order_service, wallet_service


@pytest.fixture
def crypto_pay_mock():
    mock = AsyncMock()
    mock.create_invoice.return_value = MagicMock(
        bot_invoice_url="http://t.me/invoice", invoice_id=123
    )
    return mock


@pytest.mark.asyncio
async def test_order_service_list_active_filters(session):
    # Fixed function name: get_active_orders
    await order_service.get_active_orders(
        session, fiat_currency="USD", order_type=OrderType.buy_crypto
    )


@pytest.mark.asyncio
async def test_order_service_confirm_fiat_buy_crypto(session, crypto_pay_mock):
    import uuid

    from db.models.order import Order
    from db.models.user import User

    # Corrected attribute name: telegram_id
    user = User(telegram_id=123, username="maker")
    user2 = User(telegram_id=456, username="taker")
    session.add_all([user, user2])
    await session.commit()

    order = Order(
        id=uuid.uuid4(),
        maker_id=123,
        taker_id=456,
        order_type=OrderType.buy_crypto,
        status=OrderStatus.escrow_held,
        asset="USDT",
        amount=10,
        fiat_amount=100,
        fiat_currency="USD",
        # Use string for spend_id as per model definition
        spend_id=str(uuid.uuid4()),
    )
    session.add(order)
    await session.commit()

    await order_service.confirm_fiat_payment(session, crypto_pay_mock, order_id=str(order.id))


@pytest.mark.asyncio
async def test_order_service_cancel_by_payload_not_found(session):
    res = await order_service.cancel_order_by_payload(session, payload="nonexistent")
    assert res is None


@pytest.mark.asyncio
async def test_ton_provider_memo_parse_exception():
    provider = TONProvider()
    mock_client = AsyncMock()
    tx = MagicMock()
    tx.in_msg.info.type = "int_msg"
    tx.in_msg.info.value = 100
    tx.in_msg.body = MagicMock()
    tx.in_msg.body.begin_parse.side_effect = Exception("Parse fail")

    mock_client.get_transactions.return_value = [tx]

    with patch.object(provider, "_get_client", return_value=mock_client):
        res = await provider.get_transactions("addr")
        assert len(res) == 1
        assert res[0]["memo"] == ""


def test_wallet_service_get_evm_provider_uncached():
    with patch.dict("services.wallet_service._provider_cache", {}, clear=True):
        from bot.config import settings

        with patch.object(settings, "EVM_RPC_URL", "http://evm"):
            p = wallet_service._get_provider("evm")
            assert getattr(p, "rpc_url", None) == "http://evm"
