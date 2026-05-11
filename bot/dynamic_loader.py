"""Dynamic loader for client white-label bots."""

from __future__ import annotations

import asyncio
from typing import Any

import structlog
from aiogram import Bot, Dispatcher, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.middleware import (
    BrandingMiddleware,
    CryptoPayMiddleware,
    DbSessionMiddleware,
    ThrottlingMiddleware,
    UserRegistrationMiddleware,
)
from providers.crypto_pay import CryptoPayClient

log = structlog.get_logger(__name__)


class BotInstance:
    """Container for a single client bot instance."""

    def __init__(self, bot: Bot, dp: Dispatcher):
        self.bot = bot
        self.dp = dp
        self.task: asyncio.Task[Any] | None = None

    async def start(self) -> None:
        """Start polling for this bot."""
        self.task = asyncio.create_task(self.dp.start_polling(self.bot, close_bot_session=True))
        log.info("bot_instance_started", bot_id=self.bot.id)

    async def stop(self) -> None:
        """Stop polling and close session."""
        if self.task:
            self.task.cancel()
            import contextlib

            with contextlib.suppress(asyncio.CancelledError):
                await self.task
        log.info("bot_instance_stopped", bot_id=self.bot.id)


class DynamicBotLoader:
    """Manager for multiple dynamic bot instances."""

    def __init__(
        self,
        session_pool: async_sessionmaker[AsyncSession],
        crypto_pay: CryptoPayClient,
        routers: list[Router],
    ):
        self.session_pool = session_pool
        self.crypto_pay = crypto_pay
        self.routers = routers
        self.instances: dict[str, BotInstance] = {}

    def _setup_dispatcher(self, license_id: str | None = None) -> Dispatcher:
        """Create and configure a new dispatcher for a client bot."""
        dp = Dispatcher(storage=MemoryStorage())

        if license_id:
            dp["license_id"] = license_id

        # Register middlewares
        dp.update.outer_middleware(DbSessionMiddleware(self.session_pool))
        dp.update.outer_middleware(ThrottlingMiddleware())
        dp.update.outer_middleware(UserRegistrationMiddleware())
        dp.update.outer_middleware(CryptoPayMiddleware(self.crypto_pay))
        dp.update.outer_middleware(BrandingMiddleware())

        # Include common routers
        for router in self.routers:
            dp.include_router(router)

        return dp

    async def add_bot(self, license_id: str, token: str) -> None:
        """Initialize and start a new client bot."""
        if license_id in self.instances:
            await self.remove_bot(license_id)

        bot = Bot(
            token=token,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
        dp = self._setup_dispatcher(license_id=license_id)

        instance = BotInstance(bot, dp)
        await instance.start()
        self.instances[license_id] = instance

    async def remove_bot(self, license_id: str) -> None:
        """Stop and remove a client bot."""
        instance = self.instances.pop(license_id, None)
        if instance:
            await instance.stop()

    async def stop_all(self) -> None:
        """Stop all managed bots."""
        await asyncio.gather(*(inst.stop() for inst in self.instances.values()))
        self.instances.clear()
        log.info("dynamic_loader_stopped_all")
