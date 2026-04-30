"""Bot handlers package.

All routers are registered here in ``ROUTERS``.
``main.py`` simply iterates and includes each one — no need to edit ``main.py``
when adding a new handler module.

To add a new handler:
    1. Create ``bot/handlers/my_feature.py`` with ``router = Router(name="my_feature")``.
    2. Import it here and append to ``ROUTERS``.
"""

from __future__ import annotations

from aiogram import Router

from bot.handlers import admin, chat, dispute, escrow, order, profile, start, trade, wallet

# Ordered list of routers — order matters for filter priority (more specific first)
ROUTERS: list[Router] = [
    start.router,
    order.router,
    trade.router,
    escrow.router,
    dispute.router,
    chat.router,
    profile.router,
    wallet.router,
    admin.router,   # admin last — catch-all admin filters
]

__all__ = ["ROUTERS"]
