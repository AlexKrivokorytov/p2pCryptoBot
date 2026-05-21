"""SQLAlchemy async engine and session factory.

Uses the settings singleton (bot.config.get_settings) instead of direct
os.environ access — avoids Bandit B105 and keeps DB config in one place.
"""

from __future__ import annotations

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

load_dotenv()


def _build_engine() -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    """Build the SQLAlchemy async engine using the settings singleton.

    Returns:
        Tuple of (engine, session_factory).
    """
    from bot.config import get_settings

    cfg = get_settings()
    _engine: AsyncEngine = create_async_engine(
        cfg.POSTGRES_URI,
        echo=False,
        pool_size=cfg.DB_POOL_SIZE,
        max_overflow=cfg.DB_MAX_OVERFLOW,
        pool_pre_ping=True,
    )
    _factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
        _engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    return _engine, _factory


engine, async_session_factory = _build_engine()


async def get_session() -> AsyncSession:
    """FastAPI dependency that yields a database session per request."""
    async with async_session_factory() as session:
        yield session
