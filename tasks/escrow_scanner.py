from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

if TYPE_CHECKING:
    from aiogram import Bot

from db.models.order import Order, OrderStatus
from services import notification_service
from services.order_service import _get_chain_for_asset
from services.wallet_service import _get_provider

log = structlog.get_logger(__name__)


class EscrowScanner:
    """Scanner that monitors dedicated order wallets for incoming deposits."""

    def __init__(
        self,
        bot: Bot,
        session_maker: async_sessionmaker[AsyncSession],
        interval_sec: int = 30,
    ):
        self.bot = bot
        self.session_maker = session_maker
        self.interval_sec = interval_sec
        self._running = False

    async def run(self) -> None:
        """Start the scanner loop."""
        if self._running:
            return

        self._running = True
        log.info("escrow_scanner_started", interval=self.interval_sec)

        while self._running:
            try:
                await self._scan_once()
            except Exception as e:
                log.error("escrow_scanner_error", error=str(e), exc_info=True)

            await asyncio.sleep(self.interval_sec)

    def stop(self) -> None:
        """Stop the scanner loop."""
        self._running = False
        log.info("escrow_scanner_stopped")

    async def _scan_once(self) -> None:
        """Check balances of all orders awaiting on-chain deposit."""
        async with self.session_maker() as session:
            # Fetch orders awaiting deposit
            stmt = select(Order).where(
                Order.status == OrderStatus.pending_funding,
                Order.escrow_wallet_address.is_not(None),
                Order.on_chain_status == "awaiting_deposit",
            )
            result = await session.execute(stmt)
            orders = result.scalars().all()

            if not orders:
                return

            for order in orders:
                try:
                    await self._check_order_deposit(session, order)
                except Exception as e:
                    log.warning(
                        "escrow_scanner_order_check_failed",
                        order_id=str(order.id),
                        error=str(e),
                    )

            # Commit any changes (activations)
            await session.commit()

    async def _check_order_deposit(self, session: AsyncSession, order: Order) -> None:
        """Check balance for a single order and activate if funded."""
        chain = _get_chain_for_asset(order.asset)
        if not chain:
            return

        provider = _get_provider(chain)

        # Fetch current balance
        balance = await provider.get_balance(order.escrow_wallet_address, order.asset)

        # Required amount (Maker must fund full amount + gas buffer for release)
        required = Decimal(str(order.amount)) + Decimal(str(order.on_chain_gas_buffer))

        if balance >= required:
            log.info(
                "escrow_deposit_detected",
                order_id=str(order.id),
                address=order.escrow_wallet_address,
                balance=str(balance),
                required=str(required),
            )

            # Mark as detected locally in the transaction
            order.on_chain_status = "deposit_detected"

            # Activate order (makes it visible in Order Book)
            # activate_order handles the status transition to OrderStatus.active
            # Note: activate_order starts its own transaction, but here we are already in one.
            # We'll call the logic directly or ensure session sharing.
            # To avoid nested transaction issues, we should use a non-transactional version.
            # For now, let's just update the status directly since we are already in a session.

            order.status = OrderStatus.active

            log.info(
                "order_activated_on_chain",
                order_id=str(order.id),
                status=order.status,
                step="EscrowScanner._check_order_deposit",
            )

            # Notify Maker
            await notification_service.notify_maker_order_activated(
                self.bot,
                order.maker_id,
                str(order.id),
                order.asset,
                float(order.amount),
            )

            if order.taker_id:
                await notification_service.notify_taker_order_activated(
                    self.bot,
                    order.taker_id,
                    str(order.id),
                    order.asset,
                    float(order.amount),
                )
        else:
            # Log periodically or only on change? For now, silence.
            pass
