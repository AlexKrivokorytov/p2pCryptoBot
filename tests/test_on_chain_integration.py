import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from db.models.order import Order, OrderStatus, OrderType
from db.models.user import User
from services import order_service
from tasks.escrow_scanner import EscrowScanner


@pytest.mark.integration
@pytest.mark.asyncio
async def test_on_chain_escrow_full_flow(engine, mock_crypto_pay):
    """Test the full lifecycle of an on-chain order: create -> fund -> scan -> release."""

    from sqlalchemy.ext.asyncio import async_sessionmaker

    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    maker_id = 12345
    taker_id = 67890

    async with session_factory() as session:
        # Create users
        session.add(User(telegram_id=maker_id, username="maker"))
        session.add(User(telegram_id=taker_id, username="taker"))
        await session.commit()

    asset = "TON"
    amount = Decimal("10.0")

    # 1. Create Order (Maker sells crypto)
    async with session_factory() as session:
        with patch(
            "services.wallet_service.generate_order_wallet",
            return_value={
                "address": "TEST_ADDR",
                "private_key": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
            },
        ):
            result = await order_service.create_order(
                session,
                mock_crypto_pay,
                maker_id=maker_id,
                order_type=OrderType.sell_crypto,
                asset=asset,
                amount=amount,
                fiat_currency="USD",
                fiat_amount=Decimal("50.0"),
                payment_method="Bank",
            )
        order_id = result["order_id"]

    # 2. Simulate Deposit and Run Scanner
    mock_provider = AsyncMock()
    # Add gas buffer to ensure activation (0.05 is the default for TON)
    mock_provider.get_balance.return_value = amount + Decimal("0.05")

    with patch("tasks.escrow_scanner._get_provider", return_value=mock_provider):
        mock_bot = AsyncMock()
        scanner = EscrowScanner(bot=mock_bot, session_maker=session_factory, interval_sec=1)
        await scanner._scan_once()

    # Verify activation
    async with session_factory() as session:
        stmt = select(Order).where(Order.id == uuid.UUID(order_id))
        order = (await session.execute(stmt)).scalar_one()
        assert order.status == OrderStatus.active
        assert order.on_chain_status == "deposit_detected"

    # 3. Take Order
    async with session_factory() as session:
        await order_service.take_order(session, order_id=order_id, taker_id=taker_id)

    # 4. Confirm Fiat Payment & Release Escrow
    # Mock transfer to return a fake hash
    mock_provider.transfer.return_value = "0xSUCCESS_TX_HASH"

    async with session_factory() as session:
        with patch("services.wallet_service._get_provider", return_value=mock_provider):
            # Mocking user wallet generation/lookup for taker
            with patch(
                "services.wallet_service.get_user_wallet_by_chain",
                return_value=AsyncMock(address="TAKER_ADDR"),
            ):
                await order_service.confirm_fiat_payment(
                    session, mock_crypto_pay, order_id=order_id
                )

    # Verify completion
    async with session_factory() as session:
        stmt = select(Order).where(Order.id == uuid.UUID(order_id))
        order = (await session.execute(stmt)).scalar_one()
        assert order.status == OrderStatus.completed
        assert order.on_chain_status == "released"
        assert order.on_chain_tx_hash == "0xSUCCESS_TX_HASH"
