"""Shared pytest fixtures."""

from __future__ import annotations

import importlib.util
import os
import sys
from contextlib import suppress
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from db.models.base import Base

# ---------------- Mock google.generativeai to avoid metaclass issues on import ----------------
sys.modules["google.generativeai"] = MagicMock()

# ---------------- Mock aiogram_i18n if not installed (local dev without the package) ----------

if importlib.util.find_spec("aiogram_i18n") is None:
    from typing import Generic, TypeVar
    T = TypeVar("T")

    class MockBaseCore(Generic[T]):
        def __init__(self, path: str, **kwargs: Any):
            self.path = path
        def get_locale(self, locale: str | None) -> str: return locale or "en"
        def get_translator(self, locale: str) -> T: return {} # type: ignore
        def find_locales(self) -> dict[str, T]: return {}

    class MockBaseManager:
        async def get_locale(self, *args: Any, **kwargs: Any) -> str: return "en"
        async def set_locale(self, locale: str, **kwargs: Any) -> None: pass

    class MockI18nMiddleware:
        def __init__(self, *args: Any, **kwargs: Any):
            self.core = kwargs.get("core")
            self.manager = kwargs.get("manager")

    _i18n_mock = MagicMock()
    _i18n_mock.I18nMiddleware = MockI18nMiddleware
    
    sys.modules["aiogram_i18n"] = _i18n_mock
    sys.modules["aiogram_i18n.cores"] = MagicMock()
    sys.modules["aiogram_i18n.cores.base"] = MagicMock(BaseCore=MockBaseCore)
    sys.modules["aiogram_i18n.managers"] = MagicMock()
    sys.modules["aiogram_i18n.managers.base"] = MagicMock(BaseManager=MockBaseManager)


# Mock branding to avoid file reads during tests.
# We use an autouse fixture to ensure it works across all tests.
@pytest.fixture(autouse=True)
def mock_branding(request):
    if "test_branding.py" in str(request.node.fspath):
        yield
        return
    mock_dict = {
        "bot": {
            "name": "TestP2PBot",
            "welcome_message": "Welcome to {bot_name}, {first_name}!",
            "support_handle": "@support",
            "help_text": "How P2P works:\n\n1. Step 1\n2. Step 2",
        },
        "ui": {
            "create_ad_emoji": "📝",
            "market_emoji": "🛒",
            "trades_emoji": "📋",
            "profile_emoji": "👤",
            "wallet_emoji": "💼",
            "dispute_emoji": "⚖️",
            "escrow_emoji": "🔒",
        },
        "fees": {"maker_percent": 0.0, "taker_percent": 0.0, "fixed_fee": 0.0},
        "assets_enabled": ["USDT", "TON", "BTC"],
        "payment_methods": ["Sberbank", "Tinkoff"],
        "limits": {
            "order_min_amount_usdt": 1.0,
            "order_max_amount_usdt": 50000.0,
            "order_timeout_sec": 1800,
        },
    }
    with (
        patch("bot.config.get_branding", return_value=mock_dict),
        patch("bot.config.load_branding", return_value=mock_dict),
    ):
        yield


# ---------------- Set test env vars before any imports touch os.environ ----------------
os.environ.setdefault("POSTGRES_URI", "postgresql+asyncpg://p2pbot:password@localhost:5433/p2pbot")
os.environ["AES_KEY"] = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
os.environ.setdefault("CRYPTOPAY_TOKEN", "test")
os.environ.setdefault("CRYPTOPAY_CALLBACK_SECRET", "testsecret")
os.environ.setdefault("BOT_TOKEN", "0:test")
os.environ.setdefault("ADMIN_IDS", "123456")


@pytest_asyncio.fixture(scope="session", autouse=True)
def setup_database_schema():
    from sqlalchemy import create_engine
    from sqlalchemy.pool import NullPool

    try:
        sync_uri = os.environ["POSTGRES_URI"].replace(
            "postgresql+asyncpg://", "postgresql+psycopg://"
        )
        sync_engine = create_engine(sync_uri, poolclass=NullPool)
        Base.metadata.create_all(sync_engine)
        yield
        with suppress(Exception):
            Base.metadata.drop_all(sync_engine)
        sync_engine.dispose()
    except Exception as e:
        import structlog

        log = structlog.get_logger(__name__)
        log.warning("test_db_connection_failed", error=str(e), hint="Check if DB is running")
        yield  # Allow tests that don't need DB to continue


@pytest_asyncio.fixture
async def engine():
    """Create a fresh async engine for each test."""
    _engine = create_async_engine(
        os.environ["POSTGRES_URI"],
        echo=False,
        pool_pre_ping=True,
    )
    yield _engine
    await _engine.dispose()


@pytest_asyncio.fixture
async def session(engine) -> AsyncSession:
    """Return a per-test async session. Truncates tables after each test."""
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as sess:
        yield sess

    # Cleanup after test — truncate all tables
    async with engine.begin() as conn:
        # Get table names from metadata
        table_names = [f'"{t.name}"' for t in Base.metadata.sorted_tables]
        if table_names:
            await conn.execute(text(f"TRUNCATE {', '.join(table_names)} CASCADE;"))
