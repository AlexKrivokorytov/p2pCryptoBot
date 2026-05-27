import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.order import Order, OrderStatus
from db.models.product import CurrencyType, DealStatus, MarketplaceDeal, Product
from db.models.user import User
from db.models.wallet import UserWallet, WalletChain
from services import wallet_service
from utils.encryption import encrypt

pytestmark = [pytest.mark.integration, pytest.mark.unit]


@pytest.mark.asyncio
async def test_get_provider_solana_and_tron():
    """Test lazy loading of solana and tron providers."""
    solana_provider = wallet_service._get_provider("solana")
    tron_provider = wallet_service._get_provider("tron")
    assert solana_provider is not None
    assert tron_provider is not None


@pytest.mark.asyncio
async def test_transfer_from_wallet_not_found(session: AsyncSession):
    with pytest.raises(ValueError, match="No active ton wallet found"):
        await wallet_service.transfer_from_wallet(
            session, 9999, "ton", "to_addr", "TON", Decimal("1.0")
        )


@pytest.mark.asyncio
@patch("services.wallet_service._get_provider")
async def test_transfer_from_wallet_exception(mock_get_provider, session: AsyncSession):
    async with session.begin():
        user = User(telegram_id=888, username="user888")
        session.add(user)
        wallet = UserWallet(
            user_id=888,
            chain=WalletChain.ton,
            address="addr_fail",
            encrypted_private_key=encrypt("pk_fail"),
            is_active=True,
        )
        session.add(wallet)

    provider = AsyncMock()
    provider.transfer.side_effect = Exception("rpc error")
    mock_get_provider.return_value = provider

    with pytest.raises(Exception, match="rpc error"):
        await wallet_service.transfer_from_wallet(
            session, 888, "ton", "to_addr", "TON", Decimal("1.0")
        )


@pytest.mark.asyncio
async def test_transfer_from_order_wallet_not_found(session: AsyncSession):
    order_id = str(uuid.uuid4())
    with pytest.raises(ValueError, match="No escrow wallet found for order"):
        await wallet_service.transfer_from_order_wallet(
            session, order_id, "ton", "to_addr", "TON", Decimal("1.0")
        )


@pytest.mark.asyncio
@patch("services.wallet_service._get_provider")
async def test_transfer_from_order_wallet_exception(mock_get_provider, session: AsyncSession):
    order_id = str(uuid.uuid4())
    async with session.begin():
        user = User(telegram_id=889, username="user889")
        session.add(user)
        order = Order(
            id=order_id,
            maker_id=889,
            order_type="sell_crypto",
            asset="USDT",
            amount=Decimal("100.0"),
            fiat_amount=Decimal("100.0"),
            fiat_currency="USD",
            status=OrderStatus.active,
            escrow_wallet_address="escrow_addr",
            escrow_wallet_private_key_enc=encrypt("escrow_pk"),
            on_chain_status="deposited",
        )
        session.add(order)

    provider = AsyncMock()
    provider.transfer.side_effect = Exception("order rpc error")
    mock_get_provider.return_value = provider

    with pytest.raises(Exception, match="order rpc error"):
        await wallet_service.transfer_from_order_wallet(
            session, order_id, "ton", "to_addr", "USDT", Decimal("100.0")
        )


@pytest.mark.asyncio
async def test_transfer_from_deal_wallet_not_found(session: AsyncSession):
    deal_id = str(uuid.uuid4())
    with pytest.raises(ValueError, match="No escrow wallet found for deal"):
        await wallet_service.transfer_from_deal_wallet(
            session, deal_id, "ton", "to_addr", "TON", Decimal("1.0")
        )


@pytest.mark.asyncio
@patch("services.wallet_service._get_provider")
async def test_transfer_from_deal_wallet_success_and_exception(
    mock_get_provider, session: AsyncSession
):
    deal_id = str(uuid.uuid4())
    async with session.begin():
        seller = User(telegram_id=900, username="seller900")
        buyer = User(telegram_id=901, username="buyer901")
        session.add_all([seller, buyer])
        await session.flush()

        product = Product(
            seller_id=900,
            title="Test Product",
            description="desc",
            price=Decimal("10.0"),
            currency_type=CurrencyType.CRYPTO,
            is_digital=True,
            digital_content="content",
        )
        session.add(product)
        await session.flush()

        deal = MarketplaceDeal(
            id=deal_id,
            product_id=product.id,
            buyer_id=901,
            seller_id=900,
            amount=Decimal("10.0"),
            currency_type=CurrencyType.CRYPTO,
            status=DealStatus.paid,
            escrow_wallet_address="deal_escrow",
            escrow_wallet_private_key_enc=encrypt("deal_pk"),
        )
        session.add(deal)

    provider = AsyncMock()
    provider.transfer.return_value = "deal_tx_hash"
    mock_get_provider.return_value = provider

    tx_hash = await wallet_service.transfer_from_deal_wallet(
        session, deal_id, "ton", "to_addr", "TON", Decimal("1.0")
    )
    assert tx_hash == "deal_tx_hash"

    # Exception case
    provider.transfer.side_effect = Exception("deal rpc error")
    with pytest.raises(Exception, match="deal rpc error"):
        await wallet_service.transfer_from_deal_wallet(
            session, deal_id, "ton", "to_addr", "TON", Decimal("1.0")
        )
