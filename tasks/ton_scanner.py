"""Background task to scan TON transactions for B2B payments."""

import asyncio

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from providers.ton import TONProvider
from services import b2b_service

log = structlog.get_logger(__name__)


class TONScanner:
    """Scanner that monitors a master wallet for incoming B2B payments."""

    def __init__(
        self,
        provider: TONProvider,
        session_maker: async_sessionmaker[AsyncSession],
        master_wallet: str,
        interval_sec: float = 60,
    ):
        self.provider = provider
        self.session_maker = session_maker
        self.master_wallet = master_wallet
        self.interval_sec = interval_sec
        self._running = False

    async def run(self) -> None:
        """Start the scanner loop."""
        if self._running:
            return

        self._running = True
        log.info(
            "ton_scanner_started", master_wallet=self.master_wallet, interval=self.interval_sec
        )

        while self._running:
            try:
                await self._scan_once()
            except Exception as e:
                log.error("ton_scanner_error", error=str(e), exc_info=True)

            await asyncio.sleep(self.interval_sec)

    def stop(self) -> None:
        """Stop the scanner loop."""
        self._running = False
        log.info("ton_scanner_stopped")

    async def _scan_once(self) -> None:
        """Perform a single scan of the master wallet transactions."""
        txs = await self.provider.get_transactions(self.master_wallet, limit=50)

        if not txs:
            return

        async with self.session_maker() as session:
            for tx in txs:
                memo = tx["memo"]
                if not memo or len(memo) < 8:  # Memos are UUID strings
                    continue

                # Try to process the transaction as an invoice payment
                # b2b_service.process_ton_payment will handle checking if memo is an invoice
                # and ensuring idempotency using tx_hash.
                try:
                    await b2b_service.process_ton_payment(
                        session,
                        memo=memo,
                        tx_hash=tx["hash"],
                        amount_nanotons=tx["amount_nanotons"],
                        utime=tx["utime"],
                    )
                except Exception as e:
                    log.warning(
                        "ton_scanner_payment_processing_failed",
                        tx_hash=tx["hash"],
                        memo=memo,
                        error=str(e),
                    )
