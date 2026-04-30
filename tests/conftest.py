"""Shared pytest fixtures."""

from __future__ import annotations

import os

import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from db.models.base import Base

# ── Set test env vars before any imports touch os.environ ─────────────────────
os.environ.setdefault(
    "POSTGRES_URI", "postgresql+asyncpg://p2pbot:testpassword@localhost:5432/p2pbot_test"
)
os.environ.setdefault("AES_KEY", "0" * 64)
os.environ.setdefault("CRYPTOPAY_TOKEN", "test")
os.environ.setdefault("CRYPTOPAY_CALLBACK_SECRET", "testsecret")
os.environ.setdefault("BOT_TOKEN", "0:test")
os.environ.setdefault("ADMIN_IDS", "123456")


@pytest_asyncio.fixture
async def engine():
    """Create async engine bound to the test DB."""
    _engine = create_async_engine(os.environ["POSTGRES_URI"], echo=False)
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield _engine
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await _engine.dispose()


@pytest_asyncio.fixture
async def session(engine) -> AsyncSession:
    """Return a per-test async session. Cleans up DB after each test."""
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as sess:
        yield sess

    # Cleanup after test
    async with engine.begin() as conn:
        tables = ", ".join(f'"{table.name}"' for table in Base.metadata.sorted_tables)
        if tables:
            await conn.execute(text(f"TRUNCATE {tables} CASCADE;"))
