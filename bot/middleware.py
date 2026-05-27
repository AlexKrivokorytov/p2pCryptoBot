"""Aiogram 3 middlewares for session and Crypto Pay injection.

Middlewares registered via dp.update.outer_middleware() cover all update types:
messages, callbacks, inline queries, etc.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from providers.crypto_pay import CryptoPayClient


class ThrottlingMiddleware(BaseMiddleware):
    """Simple in-memory throttling middleware to prevent spam.

    Limits users to one update per 'rate_limit' seconds.
    """

    def __init__(self, rate_limit: float = 0.5) -> None:
        self.rate_limit = rate_limit
        self.cache: dict[int, float] = {}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        from aiogram.types import CallbackQuery, Message

        user_id = None
        if (isinstance(event, Message | CallbackQuery)) and event.from_user:
            user_id = event.from_user.id

        if user_id:
            now = time.time()
            last_hit = self.cache.get(user_id, 0)
            if now - last_hit < self.rate_limit:
                # Silently ignore or answer callback if needed
                if isinstance(event, CallbackQuery):
                    await event.answer("⚠️ Slow down!", show_alert=True)
                return
            self.cache[user_id] = now

            # TTL cleanup to prevent unbounded growth
            if len(self.cache) > 5000:
                # Keep only hits within the last 10 seconds
                cutoff = now - max(10.0, self.rate_limit * 5)
                self.cache = {k: v for k, v in self.cache.items() if v >= cutoff}

        return await handler(event, data)


class DbSessionMiddleware(BaseMiddleware):
    """Inject an AsyncSession into every handler's data dict.

    Opens a new session per update and closes it automatically when the
    handler finishes (success or exception). Handlers declare ``session``
    as a parameter and aiogram injects it automatically::

        async def my_handler(message: Message, session: AsyncSession) -> None:
            ...
    """

    def __init__(self, session_pool: async_sessionmaker[AsyncSession]) -> None:
        self.session_pool = session_pool

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        async with self.session_pool() as session:
            data["session"] = session
            return await handler(event, data)


class CryptoPayMiddleware(BaseMiddleware):
    """Inject the shared CryptoPayClient into every handler's data dict.

    Handlers declare ``crypto_pay`` as a parameter::

        async def my_handler(message: Message, crypto_pay: CryptoPayClient) -> None:
            ...
    """

    def __init__(self, client: CryptoPayClient) -> None:
        self.client = client

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        data["crypto_pay"] = self.client
        return await handler(event, data)


class UserRegistrationMiddleware(BaseMiddleware):
    """Ensure every user interacting with the bot is registered in the database.

    This middleware checks if the user exists in the DB and creates a record if not.
    It runs for every update, preventing 'Profile not found' errors.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        from aiogram.types import CallbackQuery, Message

        from services.user_service import get_or_create_user

        user = None
        if isinstance(event, Message | CallbackQuery):
            user = event.from_user

        session = data.get("session")
        if user and session:
            db_user = await get_or_create_user(
                session,
                telegram_id=user.id,
                username=user.username,
                first_name=user.first_name,
            )
            data["db_user"] = db_user

        return await handler(event, data)


class BrandingMiddleware(BaseMiddleware):
    """Inject the correct branding based on the bot's license_id."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        from bot.config import load_license_branding, set_branding

        # license_id is set in dp workflow data by DynamicBotLoader
        license_id = data.get("license_id")
        session = data.get("session")

        if license_id and session:
            branding = await load_license_branding(session, license_id)
            set_branding(branding)
        else:
            # Fallback to default branding
            from bot.config import load_branding

            set_branding(load_branding())

        return await handler(event, data)
