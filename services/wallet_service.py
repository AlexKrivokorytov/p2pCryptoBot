"""Wallet service — generate and manage on-chain wallets for users."""

from __future__ import annotations

from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.wallet import UserWallet
from providers.wallet_provider import EvmWalletProvider, TonWalletProvider, WalletProvider
from utils.encryption import decrypt, encrypt

log = structlog.get_logger(__name__)

# Supported chain keys
SUPPORTED_CHAINS: frozenset[str] = frozenset({"ton", "evm"})


def get_chain_for_asset(asset: str) -> str | None:
    """Return 'ton' or 'evm' based on the asset ticker, or None if handled by CryptoPay."""
    asset_upper = asset.upper()
    if asset_upper == "TON":
        return "ton"
    if asset_upper in ("BNB", "ETH", "MATIC", "USDT", "USDC"):
        # For now, we assume these are on EVM chains
        return "evm"
    return None


# Lazy cache — providers are created on first access, not at import time
_provider_cache: dict[str, WalletProvider] = {}


def _get_provider(chain: str) -> WalletProvider:
    """Return the wallet provider for *chain*, creating it on first call.

    Providers are singletons per chain — created lazily so that
    RPC URLs (from ``settings``) are resolved at runtime, not at import time.

    Args:
        chain: Blockchain identifier ('ton' or 'evm').

    Returns:
        A ``WalletProvider`` instance for the requested chain.

    Raises:
        ValueError: If *chain* is not in ``SUPPORTED_CHAINS``.
    """
    if chain not in SUPPORTED_CHAINS:
        raise ValueError(f"Unsupported chain: {chain!r}. Supported: {sorted(SUPPORTED_CHAINS)}")
    if chain not in _provider_cache:
        from bot.config import settings  # local import avoids circular deps

        if chain == "ton":
            _provider_cache[chain] = TonWalletProvider(endpoint=settings.TON_RPC_URL)
        elif chain == "evm":
            _provider_cache[chain] = EvmWalletProvider(rpc_url=settings.EVM_RPC_URL)
    return _provider_cache[chain]


async def generate_and_save_wallet(session: AsyncSession, user_id: int, chain: str) -> UserWallet:
    """Generate a new wallet for a user on the given chain and persist it encrypted.

    Args:
        session: Active async SQLAlchemy session.
        user_id: Telegram ID of the user.
        chain: Blockchain identifier ('ton' or 'evm').

    Returns:
        The persisted ``UserWallet`` ORM object.

    Raises:
        ValueError: If *chain* is not supported.
    """
    provider = _get_provider(chain)
    wallet_data = await provider.generate_wallet(user_id)

    encrypted_pk = encrypt(wallet_data["private_key"])
    encrypted_mnemonic = encrypt(wallet_data["mnemonic"]) if wallet_data.get("mnemonic") else None

    wallet = UserWallet(
        user_id=user_id,
        chain=chain,
        address=wallet_data["address"],
        encrypted_private_key=encrypted_pk,
        encrypted_mnemonic=encrypted_mnemonic,
        is_active=True,
    )
    session.add(wallet)
    await session.flush()

    log.info(
        "wallet_generated",
        user_id=user_id,
        chain=chain,
        address=wallet_data["address"],
        step="generate_and_save_wallet",
    )
    return wallet


async def get_user_wallets(session: AsyncSession, user_id: int) -> list[UserWallet]:
    """Return all active wallets for a user ordered by creation date.

    Args:
        session: Active async SQLAlchemy session.
        user_id: Telegram ID of the user.

    Returns:
        List of ``UserWallet`` objects.
    """
    result = await session.execute(
        select(UserWallet)
        .where(UserWallet.user_id == user_id, UserWallet.is_active.is_(True))
        .order_by(UserWallet.created_at.asc())
    )
    return list(result.scalars().all())


def decrypt_wallet_key(wallet: UserWallet) -> str:
    """Decrypt and return the private key of a wallet.

    Args:
        wallet: A ``UserWallet`` ORM object.

    Returns:
        Decrypted private key string.
    """
    return decrypt(wallet.encrypted_private_key)


async def get_user_wallet_by_chain(
    session: AsyncSession, user_id: int, chain: str
) -> UserWallet | None:
    """Fetch an active wallet for a user on a specific chain.

    Args:
        session: Active async SQLAlchemy session.
        user_id: Telegram ID of the user.
        chain: Blockchain identifier ('ton' or 'evm').

    Returns:
        UserWallet object or None.
    """
    result = await session.execute(
        select(UserWallet).where(
            UserWallet.user_id == user_id,
            UserWallet.chain == chain,
            UserWallet.is_active.is_(True),
        )
    )
    return result.scalar_one_or_none()


async def generate_order_wallet(chain: str) -> dict[str, str]:
    """Generate a fresh keypair for a specific order's escrow.

    Args:
        chain: 'ton' or 'evm'.

    Returns:
        Dict with 'address', 'private_key', 'mnemonic'.
    """
    provider = _get_provider(chain)
    # Use 0 as user_id for system-generated order wallets
    wallet_data = await provider.generate_wallet(0)
    return {
        "address": wallet_data["address"],
        "private_key": wallet_data["private_key"],
        "mnemonic": wallet_data.get("mnemonic") or "",
    }


async def transfer_from_wallet(
    session: AsyncSession,
    user_id: int,
    chain: str,
    to_address: str,
    asset: str,
    amount: Any,  # Decimal
    memo: str | None = None,
) -> str:
    """Sign and broadcast a transfer from a user's wallet.

    Handles private key decryption and provider routing.

    Args:
        session: Active async SQLAlchemy session.
        user_id: Sender's Telegram ID.
        chain: Blockchain identifier.
        to_address: Recipient's public address.
        asset: Asset ticker.
        amount: Amount to transfer.
        memo: Optional transaction memo.

    Returns:
        Transaction hash.

    Raises:
        ValueError: If wallet not found or asset unsupported.
        RuntimeError: If transfer fails.
    """
    wallet = await get_user_wallet_by_chain(session, user_id, chain)
    if not wallet:
        raise ValueError(f"No active {chain} wallet found for user {user_id}")

    private_key = decrypt_wallet_key(wallet)
    provider = _get_provider(chain)

    try:
        tx_hash = await provider.transfer(
            private_key=private_key,
            to_address=to_address,
            asset=asset,
            amount=amount,
            memo=memo,
        )
        return tx_hash
    except Exception as exc:
        log.error(
            "wallet_transfer_failed",
            user_id=user_id,
            chain=chain,
            asset=asset,
            error=str(exc),
            step="transfer_from_wallet",
        )
        raise


async def transfer_from_order_wallet(
    session: AsyncSession,
    order_id: str,
    chain: str,
    to_address: str,
    asset: str,
    amount: Any,  # Decimal
    memo: str | None = None,
) -> str:
    """Sign and broadcast a transfer from an ORDER's escrow wallet.

    Args:
        session: Active async SQLAlchemy session.
        order_id: Order UUID string.
        chain: 'ton' or 'evm'.
        to_address: Recipient's public address.
        asset: Asset ticker.
        amount: Amount to transfer.
        memo: Optional transaction memo.

    Returns:
        Transaction hash.
    """
    from db.models.order import Order

    # Acquire pessimistic lock
    stmt = select(Order).where(Order.id == order_id).with_for_update()
    result = await session.execute(stmt)
    order = result.scalar_one_or_none()

    if not order or not order.escrow_wallet_private_key_enc:
        raise ValueError(f"No escrow wallet found for order {order_id}")

    private_key = decrypt(order.escrow_wallet_private_key_enc)
    provider = _get_provider(chain)

    try:
        tx_hash = await provider.transfer(
            private_key=private_key,
            to_address=to_address,
            asset=asset,
            amount=amount,
            memo=memo,
        )
        return tx_hash
    except Exception as exc:
        log.error(
            "order_transfer_failed",
            order_id=order_id,
            chain=chain,
            asset=asset,
            error=str(exc),
            step="transfer_from_order_wallet",
        )
        raise
