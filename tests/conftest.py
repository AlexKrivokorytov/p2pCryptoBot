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
@pytest.fixture(autouse=True, scope="session")
def mock_branding():
    with patch("bot.config.get_branding", return_value={}), \
         patch("bot.config.load_branding", return_value={}):
        yield

# ---------------- Set test env vars before any imports touch os.environ ----------------
os.environ.setdefault(
    "POSTGRES_URI", "postgresql+asyncpg://p2pbot:testpassword@localhost:5432/p2pbot_test"
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

    sync_uri = os.environ["POSTGRES_URI"].replace("postgresql+asyncpg://", "postgresql+psycopg2://")
    sync_engine = create_engine(sync_uri)
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
