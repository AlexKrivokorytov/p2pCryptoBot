"""Alembic environment — synchronous psycopg2 engine for reliable migrations.

WHY SYNC (psycopg2) instead of async (asyncpg):
    SQLAlchemy's asyncpg cursor wrapper ignores `create_type=False` on Enum
    columns — SQLAlchemy's internal `before_create` event fires regardless and
    attempts to CREATE TYPE even if it already exists. This is a known upstream
    issue with the async bridge. Using a synchronous engine (psycopg2) makes
    Alembic use standard DDL paths where CREATE TYPE / checkfirst work correctly.

    The app runtime still uses asyncpg — only migrations use psycopg2.
    The ALEMBIC_DB_URL env var holds the psycopg2 URL:
        postgresql+psycopg2://user:pass@host:5432/db
    The POSTGRES_URI env var holds the asyncpg URL (used by the bot):
        postgresql+asyncpg://user:pass@host:5432/db
"""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import engine_from_config, pool

load_dotenv()

# ── Alembic config ─────────────────────────────────────────────────────────────
config = context.config

# Prefer ALEMBIC_DB_URL (psycopg2).
# Fallback: auto-convert POSTGRES_URI from asyncpg → psycopg2.
_alembic_url = os.environ.get("ALEMBIC_DB_URL") or os.environ["POSTGRES_URI"].replace(
    "postgresql+asyncpg", "postgresql+psycopg2"
)
config.set_main_option("sqlalchemy.url", _alembic_url)

# Logging from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import all models so Alembic can detect schema changes
from db.models import Base  # noqa: E402

target_metadata = Base.metadata


# ── Offline mode ───────────────────────────────────────────────────────────────


def run_migrations_offline() -> None:
    """Run migrations without a live DB connection (for SQL dump generation)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


# ── Online mode (sync psycopg2) ────────────────────────────────────────────────


def run_migrations_online() -> None:
    """Run migrations with a live synchronous psycopg2 connection.

    Using synchronous engine avoids the asyncpg Enum auto-create bug.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
