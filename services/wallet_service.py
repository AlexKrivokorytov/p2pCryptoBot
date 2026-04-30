"""Wallet service — generate and manage on-chain wallets for users."""

from __future__ import annotations

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.wallet import UserWallet
from providers.wallet_provider import EvmWalletProvider, TonWalletProvider, WalletProvider
from utils.encryption import decrypt, encrypt

log = structlog.get_logger(__name__)

# Supported chain keys
SUPPORTED_CHAINS: frozenset[str] = frozenset({"ton", "evm"})

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
        raise ValueError(
            f"Unsupported chain: {chain!r}. Supported: {sorted(SUPPORTED_CHAINS)}"
        )
    if chain not in _provider_cache:
        from bot.config import settings  # local import avoids circular deps

        if chain == "ton":
            _provider_cache[chain] = TonWalletProvider(endpoint=settings.TON_RPC_URL)
        elif chain == "evm":
            _provider_cache[chain] = EvmWalletProvider(rpc_url=settings.EVM_RPC_URL)
    return _provider_cache[chain]


async def generate_and_save_wallet(
    session: AsyncSession, user_id: int, chain: str
) -> UserWallet:
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
    encrypted_mnemonic = (
        encrypt(wallet_data["mnemonic"]) if wallet_data.get("mnemonic") else None
    )

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


async def get_user_wallets(
    session: AsyncSession, user_id: int
) -> list[UserWallet]:
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
