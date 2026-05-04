"""SQLAlchemy async engine and session factory."""


from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bot.config import get_settings

load_dotenv()

_POSTGRES_URI = get_settings().POSTGRES_URI

engine = create_async_engine(
    _POSTGRES_URI,
    echo=False,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
)

async_session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    engine,
    expire_on_commit=False,
    class_=AsyncSession,
)
