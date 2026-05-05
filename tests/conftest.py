"""Shared pytest fixtures."""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from db.models.base import Base

# ---------------- Mock google.generativeai to avoid metaclass issues on import ----------------
sys.modules["google.generativeai"] = MagicMock()


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
os.environ.setdefault(
    "POSTGRES_URI", "postgresql+asyncpg://p2pbot:password@localhost:5433/p2pbot"
)
os.environ["AES_KEY"] = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
os.environ.setdefault("CRYPTOPAY_TOKEN", "test")
os.environ.setdefault("CRYPTOPAY_CALLBACK_SECRET", "testsecret")
os.environ.setdefault("BOT_TOKEN", "0:test")
os.environ.setdefault("ADMIN_IDS", "123456")


@pytest_asyncio.fixture(scope="session", autouse=True)
def setup_database_schema():
    """Create all tables once at the start of the test session using a sync engine."""
    from sqlalchemy import create_engine
    from sqlalchemy.pool import NullPool

    sync_uri = os.environ["POSTGRES_URI"].replace("postgresql+asyncpg://", "postgresql+psycopg://")
    sync_engine = create_engine(sync_uri, poolclass=NullPool)
    Base.metadata.create_all(sync_engine)
    yield
    Base.metadata.drop_all(sync_engine)
    sync_engine.dispose()


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
