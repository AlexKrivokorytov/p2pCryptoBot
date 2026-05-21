"""Tests for wallet transfers (user and order)."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.order import Order, OrderStatus
from db.models.wallet import UserWallet, WalletChain
from services import wallet_service
from utils.encryption import encrypt

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_get_user_wallet_by_chain(session: AsyncSession) -> None:
    """get_user_wallet_by_chain returns the active wallet."""
    from db.models.user import User

    async with session.begin():
        user = User(telegram_id=123, username="user123")
        session.add(user)
        wallet = UserWallet(
            user_id=123,
            chain=WalletChain.ton,
            address="addr1",
            encrypted_private_key=encrypt("pk1"),
            is_active=True,
        )
        session.add(wallet)

    res = await wallet_service.get_user_wallet_by_chain(session, 123, WalletChain.ton)
    assert res is not None
    assert res.address == "addr1"


@pytest.mark.asyncio
@patch("services.wallet_service._get_provider")
async def test_transfer_from_wallet_success(
    mock_get_provider: AsyncMock, session: AsyncSession
) -> None:
    """transfer_from_wallet calls provider.transfer with decrypted key."""
    from db.models.user import User

    async with session.begin():
        user = User(telegram_id=124, username="user124")
        session.add(user)
        wallet = UserWallet(
            user_id=124,
            chain=WalletChain.ton,
            address="addr2",
            encrypted_private_key=encrypt("pk2"),
            is_active=True,
        )
        session.add(wallet)

    provider = AsyncMock()
    provider.transfer.return_value = "tx_hash_123"
    mock_get_provider.return_value = provider

    tx_hash = await wallet_service.transfer_from_wallet(
        session, 124, "ton", "to_addr", "TON", Decimal("1.0")
    )

    assert tx_hash == "tx_hash_123"
    provider.transfer.assert_awaited_once_with(
        private_key="pk2", to_address="to_addr", asset="TON", amount=Decimal("1.0"), memo=None
    )


@pytest.mark.asyncio
@patch("services.wallet_service._get_provider")
async def test_transfer_from_order_wallet_success(
    mock_get_provider: AsyncMock, session: AsyncSession
) -> None:
    """transfer_from_order_wallet calls provider.transfer for escrow wallet."""
    import uuid

    order_id = str(uuid.uuid4())
    from db.models.user import User

    async with session.begin():
        user = User(telegram_id=125, username="user125")
        session.add(user)
        order = Order(
            id=order_id,
            maker_id=125,
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
    provider.transfer.return_value = "tx_hash_escrow"
    mock_get_provider.return_value = provider

    tx_hash = await wallet_service.transfer_from_order_wallet(
        session, order_id, "ton", "to_addr", "USDT", Decimal("100.0")
    )

    assert tx_hash == "tx_hash_escrow"
    provider.transfer.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_user_wallets(session: AsyncSession) -> None:
    """get_user_wallets returns all active wallets for a user."""
    from db.models.user import User

    async with session.begin():
        user = User(telegram_id=126, username="user126")
        session.add(user)
        session.add(
            UserWallet(
                user_id=126,
                chain=WalletChain.ton,
                address="a1",
                is_active=True,
                encrypted_private_key="p1",
            )
        )
        session.add(
            UserWallet(
                user_id=126,
                chain=WalletChain.evm,
                address="a2",
                is_active=True,
                encrypted_private_key="p2",
            )
        )
        session.add(
            UserWallet(
                user_id=126,
                chain=WalletChain.solana,
                address="a3",
                is_active=False,
                encrypted_private_key="p3",
            )
        )

    wallets = await wallet_service.get_user_wallets(session, 126)
    assert len(wallets) == 2
    addresses = {w.address for w in wallets}
    assert "a1" in addresses
    assert "a2" in addresses
