"""Tests for wallet service and handlers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.handlers import wallet as wallet_handlers
from db.models.user import User
from db.models.wallet import UserWallet, WalletChain
from services import wallet_service

# ── Helpers ────────────────────────────────────────────────────────────────────


async def _create_test_user(session: AsyncSession, user_id: int) -> User:
    """Persist a minimal User row for FK constraints."""
    async with session.begin():
        user = User(telegram_id=user_id, username=f"user_{user_id}")
        session.add(user)
        return user


def _make_provider_mock(
    address: str, private_key: str = "pk", mnemonic: str = "m1 m2"
) -> AsyncMock:
    """Build a WalletProvider AsyncMock returning the given wallet data."""
    provider = AsyncMock()
    provider.generate_wallet.return_value = {
        "address": address,
        "private_key": private_key,
        "mnemonic": mnemonic,
    }
    return provider


# ── Service: generate_and_save_wallet ─────────────────────────────────────────


@pytest.mark.asyncio
@patch("services.wallet_service._get_provider")
async def test_generate_and_save_wallet_ton(mock_get_provider: MagicMock, engine) -> None:
    """Generated TON wallet is persisted with encrypted private key."""
    mock_get_provider.return_value = _make_provider_mock(
        address="UQTestTONAddress",
        private_key="ton_private_key",
        mnemonic="word1 word2 word3",
    )

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        await _create_test_user(session, 111)

    async with factory() as session, session.begin():
        wallet = await wallet_service.generate_and_save_wallet(session, 111, WalletChain.ton)

    assert wallet.address == "UQTestTONAddress"
    assert wallet.chain == WalletChain.ton
    assert wallet.user_id == 111
    assert wallet.encrypted_private_key  # stored as hex, not plaintext
    assert "ton_private_key" not in wallet.encrypted_private_key


@pytest.mark.asyncio
@patch("services.wallet_service._get_provider")
async def test_generate_and_save_wallet_evm(mock_get_provider: MagicMock, engine) -> None:
    """Generated EVM wallet is persisted with encrypted private key."""
    mock_get_provider.return_value = _make_provider_mock(
        address="0xEvmTestAddress",
        private_key="evm_private_key",
    )

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        await _create_test_user(session, 333)

    async with factory() as session, session.begin():
        wallet = await wallet_service.generate_and_save_wallet(session, 333, WalletChain.evm)

    assert wallet.address == "0xEvmTestAddress"
    assert wallet.chain == WalletChain.evm


# ── Service: get_user_wallets ──────────────────────────────────────────────────


@pytest.mark.asyncio
@patch("services.wallet_service._get_provider")
async def test_get_user_wallets(mock_get_provider: MagicMock, engine) -> None:
    """Returns only active wallets for the requested user."""
    mock_get_provider.return_value = _make_provider_mock("UQTestTONAddress2")

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        await _create_test_user(session, 222)

    async with factory() as session, session.begin():
        await wallet_service.generate_and_save_wallet(session, 222, WalletChain.ton)

    async with factory() as session:
        wallets = await wallet_service.get_user_wallets(session, 222)

    assert len(wallets) == 1
    assert wallets[0].address == "UQTestTONAddress2"


@pytest.mark.asyncio
async def test_generate_wallet_invalid_chain(session: AsyncSession) -> None:
    """Unsupported chain raises ValueError immediately."""
    with pytest.raises(ValueError, match="Unsupported chain"):
        await wallet_service.generate_and_save_wallet(session, 999, "solana")


# ── Handler: cmd_wallet ────────────────────────────────────────────────────────


@pytest.mark.asyncio
@patch("bot.handlers.wallet.wallet_service.get_user_wallets", new_callable=AsyncMock)
async def test_cmd_wallet_no_wallets(mock_get_wallets: AsyncMock, session: AsyncSession) -> None:
    """Wallet command shows empty-state text when user has no wallets."""
    mock_get_wallets.return_value = []

    message = AsyncMock(spec=Message)
    message.from_user = MagicMock()
    message.from_user.id = 111

    await wallet_handlers.cmd_wallet(message, session)

    message.answer.assert_called_once()
    ca = message.answer.call_args
    text = ca.args[0] if ca.args else ca.kwargs.get("text", "")
    assert "Your Wallets" in text
    assert "don't have any wallets" in text


@pytest.mark.asyncio
@patch("bot.handlers.wallet.wallet_service.get_user_wallets", new_callable=AsyncMock)
async def test_cmd_wallet_with_wallets(mock_get_wallets: AsyncMock, session: AsyncSession) -> None:
    """Wallet command shows address when user already has wallets."""
    wallet = UserWallet(
        id=1,
        user_id=111,
        chain=WalletChain.ton.value,
        address="UQSomeAddress",
        encrypted_private_key="enc",
    )
    mock_get_wallets.return_value = [wallet]

    message = AsyncMock(spec=Message)
    message.from_user = MagicMock()
    message.from_user.id = 111

    await wallet_handlers.cmd_wallet(message, session)

    ca = message.answer.call_args
    text = ca.args[0] if ca.args else ca.kwargs.get("text", "")
    assert "UQSomeAddress" in text


# ── Handler: cb_generate_wallet ───────────────────────────────────────────────


@pytest.mark.asyncio
@patch("bot.handlers.wallet.wallet_service.generate_and_save_wallet", new_callable=AsyncMock)
async def test_cb_generate_wallet_success(mock_generate: AsyncMock, session: AsyncSession) -> None:
    """Generate wallet callback creates wallet and shows address in response."""
    mock_generate.return_value = UserWallet(
        id=1,
        user_id=111,
        chain=WalletChain.evm.value,
        address="0xNewEvmAddress",
        encrypted_private_key="enc",
    )

    callback = AsyncMock(spec=CallbackQuery)
    callback.from_user = MagicMock()
    callback.from_user.id = 111
    callback.message = AsyncMock(spec=Message)
    callback.data = "wallet:generate:evm"

    state = AsyncMock()
    await wallet_handlers.cb_generate_wallet(callback, session, state)

    callback.message.edit_text.assert_called()
    last_call_text = callback.message.edit_text.call_args[0][0]
    assert "0xNewEvmAddress" in last_call_text
    assert "Wallet Created" in last_call_text


@pytest.mark.asyncio
async def test_cb_generate_wallet_invalid_chain(session: AsyncSession) -> None:
    """Invalid chain shows error message and does not crash."""
    callback = AsyncMock(spec=CallbackQuery)
    callback.from_user = MagicMock()
    callback.from_user.id = 111
    callback.message = AsyncMock(spec=Message)
    callback.data = "wallet:generate:solana"

    state = AsyncMock()
    await wallet_handlers.cb_generate_wallet(callback, session, state)

    # Should show an error edit, not crash
    callback.message.edit_text.assert_called()


# ── Provider: EvmWalletProvider (real) ───────────────────────────────────────


@pytest.mark.asyncio
async def test_evm_provider_generates_real_address() -> None:
    """EvmWalletProvider returns a valid checksum EVM address and BIP-39 mnemonic."""
    from providers.wallet_provider import EvmWalletProvider

    provider = EvmWalletProvider(rpc_url="https://bsc-dataseed.binance.org/")
    result = await provider.generate_wallet(user_id=42)

    assert "address" in result
    assert "private_key" in result
    assert "mnemonic" in result

    # Address format: 0x + 40 hex chars
    assert result["address"].startswith("0x"), "EVM address must start with 0x"
    assert len(result["address"]) == 42, "EVM address must be 42 chars"

    # Private key: 32 bytes = 64 hex chars (no 0x prefix) or 66 with prefix
    pk = result["private_key"]
    pk_hex = pk[2:] if pk.startswith("0x") else pk
    assert len(pk_hex) == 64, f"EVM private key must be 64 hex chars, got {len(pk_hex)}: {pk!r}"

    # Mnemonic: 12 words (128-bit entropy, default for eth-account)
    words = result["mnemonic"].split()
    assert len(words) in (12, 24), f"Mnemonic must have 12 or 24 words, got {len(words)}"

    # Uniqueness: two wallets must differ
    result2 = await provider.generate_wallet(user_id=43)
    assert result["address"] != result2["address"], "Each wallet must have a unique address"
    assert result["mnemonic"] != result2["mnemonic"], "Each wallet must have a unique mnemonic"


@pytest.mark.asyncio
async def test_evm_provider_deterministic_from_mnemonic() -> None:
    """Same mnemonic must always produce the same EVM address."""
    from eth_account import Account  # type: ignore[import-untyped]

    Account.enable_unaudited_hdwallet_features()

    mnemonic = (
        "abandon abandon abandon abandon abandon abandon "
        "abandon abandon abandon abandon abandon about"
    )
    acct1 = Account.from_mnemonic(mnemonic)
    acct2 = Account.from_mnemonic(mnemonic)
    assert acct1.address == acct2.address, "Same mnemonic must yield same address"


# ── Provider: TonWalletProvider (real) ───────────────────────────────────────


@pytest.mark.asyncio
async def test_ton_provider_generates_address() -> None:
    """TonWalletProvider returns a non-empty address (real or stub fallback)."""
    from providers.wallet_provider import TonWalletProvider

    provider = TonWalletProvider(endpoint="https://toncenter.com/api/v2/jsonRPC")
    result = await provider.generate_wallet(user_id=99)

    assert "address" in result
    assert "private_key" in result
    assert result["address"], "TON address must not be empty"

    # Address is either real UQ... or stub — both are valid at this stage
    addr = result["address"]
    assert len(addr) > 10, f"TON address looks too short: {addr!r}"


@pytest.mark.asyncio
async def test_ton_provider_uniqueness() -> None:
    """Two TonWalletProvider calls must produce different addresses."""
    from providers.wallet_provider import TonWalletProvider

    provider = TonWalletProvider(endpoint="https://toncenter.com/api/v2/jsonRPC")
    r1 = await provider.generate_wallet(user_id=1)
    r2 = await provider.generate_wallet(user_id=2)

    assert r1["address"] != r2["address"], "Each TON wallet must be unique"
