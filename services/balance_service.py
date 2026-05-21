"""Balance service — aggregate on-chain balances for all user wallets.

Design:
- Fetches balances for predefined assets per chain in parallel (asyncio.gather).
- Each balance fetch is protected with a timeout; failures return 0 without crashing.
- The result is a structured dict ready for formatting in the UI layer.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from decimal import Decimal

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.wallet import UserWallet
from services import wallet_service as ws
from services.wallet_service import _get_provider  # re-exported for test patching

log = structlog.get_logger(__name__)

# Assets to display per chain
_CHAIN_ASSETS: dict[str, list[str]] = {
    "evm": ["BNB", "USDT", "USDC"],
    "ton": ["TON"],
    "solana": ["SOL"],
    "tron": ["TRX"],
}

# Timeout per individual balance request
_BALANCE_TIMEOUT_SEC = 8


@dataclass
class WalletBalance:
    """Balance snapshot for a single wallet."""

    wallet: UserWallet
    balances: dict[str, Decimal] = field(default_factory=dict)  # {asset: amount}
    error: bool = False


async def _fetch_single_balance(wallet: UserWallet, asset: str) -> tuple[str, Decimal]:
    """Fetch one asset balance with timeout protection.

    Args:
        wallet: The wallet to query.
        asset: Asset ticker to fetch.

    Returns:
        (asset, balance) tuple. Returns (asset, Decimal("0")) on any error.
    """
    try:
        provider = _get_provider(wallet.chain)
        balance = await asyncio.wait_for(
            provider.get_balance(wallet.address, asset),
            timeout=_BALANCE_TIMEOUT_SEC,
        )
        return asset, balance
    except TimeoutError:
        log.warning(
            "balance_timeout",
            address=wallet.address,
            asset=asset,
            chain=wallet.chain,
            step="_fetch_single_balance",
        )
        return asset, Decimal("0")
    except Exception as exc:
        log.warning(
            "balance_fetch_error",
            address=wallet.address,
            asset=asset,
            chain=wallet.chain,
            error=str(exc),
            step="_fetch_single_balance",
        )
        return asset, Decimal("0")


async def get_portfolio_balances(session: AsyncSession, user_id: int) -> list[WalletBalance]:
    """Fetch balances for all active wallets of a user in parallel.

    For each wallet, queries all predefined assets concurrently.

    Args:
        session: Active async SQLAlchemy session.
        user_id: Telegram ID of the user.

    Returns:
        List of :class:`WalletBalance` objects, one per wallet.
    """
    wallets = await ws.get_user_wallets(session, user_id)
    if not wallets:
        return []

    results: list[WalletBalance] = []

    for wallet in wallets:
        assets = _CHAIN_ASSETS.get(wallet.chain, [])
        if not assets:
            results.append(WalletBalance(wallet=wallet))
            continue

        # Fetch all assets for this wallet concurrently
        tasks = [_fetch_single_balance(wallet, asset) for asset in assets]
        pairs = await asyncio.gather(*tasks)
        balances = {asset: amount for asset, amount in pairs}

        results.append(WalletBalance(wallet=wallet, balances=balances))
        log.info(
            "portfolio_balance_fetched",
            user_id=user_id,
            chain=wallet.chain,
            address=wallet.address,
            step="get_portfolio_balances",
        )

    return results
