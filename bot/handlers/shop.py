"""Shop handlers — category navigation and product browsing (scaffold).

Callbacks:
    - shop:menu
    - shop:cat:{id}
    - shop:cat:{id}:{page}
    - shop:search
"""

from __future__ import annotations

import structlog
from aiogram import Router

log = structlog.get_logger(__name__)
router = Router(name="shop")
