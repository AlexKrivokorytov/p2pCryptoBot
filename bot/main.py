"""Bot entry point — initialises dispatcher, registers middleware and routers.

Startup sequence:
  1. Load .env and validate required secrets via ``bot.config.settings``.
  2. Create async SQLAlchemy engine + session factory.
  3. Create CryptoPayClient.
  4. Register outer middlewares (session, crypto_pay) on dp.update.
  5. Include all routers from ``bot.handlers.ROUTERS``.
  6. Start aiohttp webhook server for Crypto Pay callbacks.
  7. Start background cleanup task.
  8. Start Telegram polling.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

import structlog
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiohttp import web
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

load_dotenv()  # Must happen before importing settings

from bot.config import settings  # noqa: E402
from bot.handlers import ROUTERS  # noqa: E402
from bot.handlers.webhook import cryptopay_webhook  # noqa: E402
from bot.middleware import CryptoPayMiddleware, DbSessionMiddleware  # noqa: E402
from providers.crypto_pay import CryptoPayClient  # noqa: E402
from tasks.cleanup import start_cleanup_task  # noqa: E402
from utils.license_guard import check_license_or_abort  # noqa: E402
from bot.i18n import setup_i18n  # noqa: E402
from aiogram_i18n import I18nMiddleware  # noqa: E402

# ── Structlog setup ─────────────────────────────────────────────────────────────
structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer(),
    ],
)
log = structlog.get_logger(__name__)


async def main() -> None:
    """Bootstrap the bot and start polling."""
    # ── License check — must pass before any other resource is initialised ──────
    check_license_or_abort(settings.BOT_TOKEN)

    # ── Database engine & session factory ───────────────────────────────────────
    engine = create_async_engine(
        settings.POSTGRES_URI,
        pool_pre_ping=True,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
    )
    session_pool = async_sessionmaker(engine, expire_on_commit=False)

    # ── Crypto Pay client ───────────────────────────────────────────────────────
    crypto_pay = CryptoPayClient()

    # ── Aiogram Bot + Dispatcher ────────────────────────────────────────────────
    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    # Outer middlewares — cover ALL update types (message, callback, inline, …)
    dp.update.outer_middleware(DbSessionMiddleware(session_pool))
    dp.update.outer_middleware(CryptoPayMiddleware(crypto_pay))
    
    # I18n setup
    i18n = setup_i18n()
    i18n.setup(dispatcher=dp)

    # ── Routers — auto-registered from bot.handlers.ROUTERS ─────────────────────
    for router in ROUTERS:
        dp.include_router(router)

    # ── Crypto Pay webhook server ────────────────────────────────────────────────
    app = web.Application()
    app["crypto_pay"] = crypto_pay
    app["session_pool"] = session_pool
    app.router.add_post(settings.CRYPTOPAY_WEBHOOK_PATH, cryptopay_webhook)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", settings.WEBHOOK_PORT)  # nosec B104: required for Docker
    await site.start()
    log.info(
        "webhook_server_started",
        port=settings.WEBHOOK_PORT,
        path=settings.CRYPTOPAY_WEBHOOK_PATH,
    )

    # ── Background cleanup task ──────────────────────────────────────────────────
    cleanup_task = asyncio.create_task(start_cleanup_task(session_pool, bot))

    log.info("bot_starting", mode="polling")
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        cleanup_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await cleanup_task
        await crypto_pay.close()
        await bot.session.close()
        await engine.dispose()
        await runner.cleanup()
        log.info("bot_stopped")


if __name__ == "__main__":
    asyncio.run(main())
