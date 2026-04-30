"""Aiogram 3 middlewares for session and Crypto Pay injection.

Middlewares registered via dp.update.outer_middleware() cover all update types:
messages, callbacks, inline queries, etc.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from providers.crypto_pay import CryptoPayClient


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
