"""Centralized application configuration.

All environment variables are read and validated here.
Import ``settings`` from this module anywhere in the application.

Usage::

    from bot.config import settings

    engine = create_async_engine(settings.POSTGRES_URI)
    bot = Bot(token=settings.BOT_TOKEN)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


def _require(key: str) -> str:
    """Read a required environment variable or raise a descriptive error."""
    value = os.environ.get(key, "").strip()
    if not value:
        raise RuntimeError(
            f"Missing required environment variable: {key!r}. Ensure it is set in your .env file."
        )
    return value


def _optional(key: str, default: str = "") -> str:
    """Read an optional environment variable with a fallback default."""
    return os.environ.get(key, default).strip()


@dataclass(frozen=True, slots=True)
class Settings:
    """Immutable application settings validated at startup."""

    # ── Telegram ─────────────────────────────────────────────────────────────
    BOT_TOKEN: str

    # ── Database ──────────────────────────────────────────────────────────────
    POSTGRES_URI: str  # asyncpg URI for the bot runtime
    ALEMBIC_DB_URL: str  # psycopg URI for Alembic migrations

    # ── Crypto Pay ────────────────────────────────────────────────────────────
    CRYPTOPAY_TOKEN: str
    CRYPTOPAY_CALLBACK_SECRET: str
    CRYPTOPAY_WEBHOOK_PATH: str

    # ── Encryption ────────────────────────────────────────────────────────────
    AES_KEY: str  # 64-char hex string (32 bytes)

    # ── Admins ────────────────────────────────────────────────────────────────
    ADMIN_IDS: frozenset[int]

    # ── Order settings ────────────────────────────────────────────────────────
    ORDER_TIMEOUT_SEC: int
    ORDER_MIN_AMOUNT_USDT: float
    ORDER_MAX_AMOUNT_USDT: float

    # ── Web server ────────────────────────────────────────────────────────────
    WEBHOOK_PORT: int

    # ── Web3 RPC endpoints ────────────────────────────────────────────────────
    TON_RPC_URL: str
    EVM_RPC_URL: str

    # ── AI mediator ───────────────────────────────────────────────────────────
    GEMINI_API_KEY: str

    # ── B2B SaaS settings ─────────────────────────────────────────────────────
    B2B_LICENSE_PRICE_STARS: int
    MASTER_BOT_USERNAME: str
    MASTER_TON_WALLET: str

    # ── DB pool ───────────────────────────────────────────────────────────────
    DB_POOL_SIZE: int = field(default=10)
    DB_MAX_OVERFLOW: int = field(default=20)


def _parse_admin_ids(raw: str) -> frozenset[int]:
    """Parse comma-separated admin Telegram IDs."""
    if not raw:
        return frozenset()
    return frozenset(int(x.strip()) for x in raw.split(",") if x.strip().isdigit())


def load_settings() -> Settings:
    """Build and return a validated Settings instance from environment variables."""
    return Settings(
        BOT_TOKEN=_require("BOT_TOKEN"),
        POSTGRES_URI=_require("POSTGRES_URI"),
        ALEMBIC_DB_URL=_optional(
            "ALEMBIC_DB_URL",
            _require("POSTGRES_URI").replace("+asyncpg", "+psycopg"),
        ),
        CRYPTOPAY_TOKEN=_require("CRYPTOPAY_TOKEN"),
        CRYPTOPAY_CALLBACK_SECRET=_require("CRYPTOPAY_CALLBACK_SECRET"),
        CRYPTOPAY_WEBHOOK_PATH=_optional("CRYPTOPAY_WEBHOOK_PATH", "/webhook/cryptopay"),
        AES_KEY=_require("AES_KEY"),
        ADMIN_IDS=_parse_admin_ids(_optional("ADMIN_IDS")),
        ORDER_TIMEOUT_SEC=int(_optional("ORDER_TIMEOUT_SEC", "1800")),
        ORDER_MIN_AMOUNT_USDT=float(_optional("ORDER_MIN_AMOUNT_USDT", "1.0")),
        ORDER_MAX_AMOUNT_USDT=float(_optional("ORDER_MAX_AMOUNT_USDT", "50000.0")),
        WEBHOOK_PORT=int(_optional("WEBHOOK_PORT", "8080")),
        TON_RPC_URL=_optional("TON_RPC_URL", "https://toncenter.com/api/v2/jsonRPC"),
        EVM_RPC_URL=_optional("EVM_RPC_URL", "https://bsc-dataseed.binance.org/"),
        GEMINI_API_KEY=_optional("GEMINI_API_KEY"),
        B2B_LICENSE_PRICE_STARS=int(_optional("B2B_LICENSE_PRICE_STARS", "10000")),
        MASTER_BOT_USERNAME=_optional("MASTER_BOT_USERNAME", "p2p_master_bot"),
        MASTER_TON_WALLET=_require("MASTER_TON_WALLET"),
        DB_POOL_SIZE=int(_optional("DB_POOL_SIZE", "10")),
        DB_MAX_OVERFLOW=int(_optional("DB_MAX_OVERFLOW", "20")),
    )


# Module-level singleton — loaded once on first access.
# We defer creation to a function so that unit tests can set env vars in conftest.py
# before the first call to get_settings(), avoiding "missing env var" errors at import time.
_settings_cache: Settings | None = None


def get_settings() -> Settings:
    """Return the application settings singleton, creating it on first call."""
    global _settings_cache  # noqa: PLW0603
    if _settings_cache is None:
        _settings_cache = load_settings()
    return _settings_cache


_branding_cache: dict[str, Any] | None = None


def load_branding() -> dict[str, Any]:
    """Load branding configuration from branding.yaml.

    Returns:
        Parsed branding dict with all customization values.

    Raises:
        RuntimeError: If branding.yaml is not found in the project root.
    """
    global _branding_cache  # noqa: PLW0603
    if _branding_cache is not None:
        return _branding_cache
    path = Path("branding.yaml")
    if not path.exists():
        raise RuntimeError(
            "branding.yaml not found in project root. "
            "Copy branding.yaml.example to branding.yaml and customize it."
        )
    with open(path, encoding="utf-8") as f:
        _branding_cache = yaml.safe_load(f)
    return _branding_cache


def get_branding() -> dict[str, Any]:
    """Return the branding configuration singleton.

    Returns:
        Parsed branding dict. Cached after first call.
    """
    return load_branding()


def _reset_branding_cache() -> None:
    """Reset branding cache — for use in tests only."""
    global _branding_cache  # noqa: PLW0603
    _branding_cache = None


# Convenience alias — use ``settings`` for direct attribute access.
# In tests, env vars set in conftest.py will be picked up because conftest
# runs before any production code imports trigger get_settings().
class _LazySettings:
    """Proxy that defers Settings creation until first attribute access."""

    def __getattr__(self, name: str) -> object:
        return getattr(get_settings(), name)

    def __repr__(self) -> str:
        return repr(get_settings())


settings: Settings = _LazySettings()  # type: ignore[assignment]
