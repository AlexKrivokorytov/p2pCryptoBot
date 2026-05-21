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

from bot.handlers import (
    admin,
    admin_sandbox,
    b2b,
    chat,
    dispute,
    escrow,
    marketplace,
    order,
    profile,
    settings,
    stars_payment,
    start,
    trade,
    wallet,
)

ROUTERS: list[Router] = [
    start.router,
    marketplace.router,  # marketplace before order — ad callbacks take priority
    order.router,
    trade.router,
    escrow.router,
    dispute.router,
    chat.router,
    profile.router,
    wallet.router,
    settings.router,
    b2b.router,
    stars_payment.router,
    admin.router,  # admin last — catch-all admin filters
    admin_sandbox.router,
]

__all__ = ["ROUTERS"]
