"""Database initialization script — drop, recreate, migrate, and seed.

Replaces the combination of migrate.sh + manual SQL.

Usage (from project root, with .env loaded):
    python scripts/init_db.py                  # Migrate + seed (safe, idempotent)
    python scripts/init_db.py --reset          # DROP all tables, then migrate + seed
    python scripts/init_db.py --reset --yes    # Same, but skip confirmation prompt

The script:
    1. Optionally drops all public tables (--reset).
    2. Drops stale alembic_version if the schema is empty.
    3. Runs ``alembic upgrade head`` via subprocess (uses ALEMBIC_DB_URL / psycopg).
    4. Seeds reference data using the async engine (asyncpg) — idempotent INSERT OR IGNORE.

Environment variables required (loaded from .env automatically):
    POSTGRES_URI       asyncpg URI, e.g. postgresql+asyncpg://user:pass@host/db
    AES_KEY            64-char hex (32 bytes) — required by settings import
    BOT_TOKEN          Telegram bot token — required by settings import
    CRYPTOPAY_TOKEN    CryptoPay API token — required by settings import
    CRYPTOPAY_CALLBACK_SECRET  Webhook secret — required by settings import
    MASTER_TON_WALLET  TON wallet address — required by settings import
"""

from __future__ import annotations

import argparse
import asyncio
import os
import subprocess
import sys
from pathlib import Path

# ── Bootstrap: add project root to sys.path ───────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(PROJECT_ROOT / ".env")

import structlog  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

log = structlog.get_logger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Seed data
# ─────────────────────────────────────────────────────────────────────────────

# Payment methods seeded into the `payment_methods` table.
# Each entry: (name, currency, is_active)
PAYMENT_METHODS: list[tuple[str, str, bool]] = [
    # ── RUB ──────────────────────────────────────────────────
    ("Сбербанк", "RUB", True),
    ("Тинькофф (Т-Банк)", "RUB", True),
    ("ВТБ", "RUB", True),
    ("Альфа-Банк", "RUB", True),
    ("Райффайзенбанк", "RUB", True),
    ("СБП (Система быстрых платежей)", "RUB", True),
    ("Наличные RUB", "RUB", True),
    # ── UAH ──────────────────────────────────────────────────
    ("Приват24 (ПриватБанк)", "UAH", True),
    ("Монобанк", "UAH", True),
    ("ПУМБ", "UAH", True),
    ("Наличные UAH", "UAH", True),
    # ── KZT ──────────────────────────────────────────────────
    ("Kaspi Bank", "KZT", True),
    ("Халык Банк", "KZT", True),
    ("Наличные KZT", "KZT", True),
    # ── USD ──────────────────────────────────────────────────
    ("Revolut", "USD", True),
    ("Wise", "USD", True),
    ("PayPal", "USD", True),
    ("SWIFT (USD)", "USD", True),
    ("Наличные USD", "USD", True),
    # ── EUR ──────────────────────────────────────────────────
    ("SEPA (EUR)", "EUR", True),
    ("Revolut EUR", "EUR", True),
    ("Wise EUR", "EUR", True),
    ("Наличные EUR", "EUR", True),
    # ── TRY ──────────────────────────────────────────────────
    ("Papara", "TRY", True),
    ("Ziraat Bankası", "TRY", True),
    ("Наличные TRY", "TRY", True),
    # ── GBP ──────────────────────────────────────────────────
    ("UK Bank Transfer", "GBP", True),
    ("Monzo", "GBP", True),
    # ── Universal ─────────────────────────────────────────────
    ("Другое", "ANY", True),
]


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _get_alembic_url() -> str:
    """Build the psycopg URL for Alembic from environment variables.

    Returns:
        Connection URL string for Alembic (psycopg dialect).

    Raises:
        SystemExit: If no DB URL is configured.
    """
    url = os.getenv("ALEMBIC_DB_URL") or os.getenv("POSTGRES_URI", "")
    if not url:
        print("ERROR: POSTGRES_URI or ALEMBIC_DB_URL must be set in .env", file=sys.stderr)
        sys.exit(1)
    # Normalise to psycopg (sync) dialect required by Alembic
    return url.replace("postgresql+asyncpg://", "postgresql+psycopg://")


def _get_asyncpg_url() -> str:
    """Build the asyncpg URL for the async engine.

    Returns:
        Connection URL string for the async SQLAlchemy engine.

    Raises:
        SystemExit: If no DB URL is configured.
    """
    url = os.getenv("POSTGRES_URI", "")
    if not url:
        print("ERROR: POSTGRES_URI must be set in .env", file=sys.stderr)
        sys.exit(1)
    return url.replace("postgresql+psycopg://", "postgresql+asyncpg://")


def _parse_psql_params(url: str) -> dict[str, str]:
    """Extract host, port, user, password, dbname from a psycopg URL.

    Args:
        url: psycopg connection URL, e.g.
            ``postgresql+psycopg://user:pass@host:5432/dbname``.

    Returns:
        Dict with keys ``host``, ``port``, ``user``, ``password``, ``dbname``.
    """
    import re

    pattern = r"postgresql(?:\+psycopg)?://([^:]+):([^@]+)@([^:/]+):?(\d*)/(.+)"
    m = re.match(pattern, url)
    if not m:
        return {}
    return {
        "user": m.group(1),
        "password": m.group(2),
        "host": m.group(3),
        "port": m.group(4) or "5432",
        "dbname": m.group(5),
    }


def _table_exists(params: dict[str, str], table: str) -> bool:
    """Return True if *table* exists in the public schema.

    Args:
        params: DB connection parameters dict from :func:`_parse_psql_params`.
        table: Table name to check.

    Returns:
        True if the table exists, False otherwise.
    """
    import psycopg

    dsn = (
        f"host={params['host']} port={params['port']} "
        f"dbname={params['dbname']} user={params['user']} "
        f"password={params['password']}"
    )
    try:
        with psycopg.connect(dsn) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT EXISTS (SELECT FROM information_schema.tables "
                "WHERE table_schema='public' AND table_name=%s);",
                (table,),
            )
            row = cur.fetchone()
            return bool(row and row[0])
    except Exception as exc:
        log.warning("table_check_failed", table=table, error=str(exc))
        return False


def _drop_all_tables(params: dict[str, str]) -> None:
    """Drop all tables in the public schema (irreversible!).

    Args:
        params: DB connection parameters dict from :func:`_parse_psql_params`.
    """
    import psycopg

    dsn = (
        f"host={params['host']} port={params['port']} "
        f"dbname={params['dbname']} user={params['user']} "
        f"password={params['password']}"
    )
    with psycopg.connect(dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT tablename FROM pg_tables WHERE schemaname='public';")
            tables = [row[0] for row in cur.fetchall()]
            if tables:
                names = ", ".join(f'"{t}"' for t in tables)
                cur.execute(f"DROP TABLE IF EXISTS {names} CASCADE;")
                log.info("tables_dropped", count=len(tables))
            else:
                log.info("no_tables_to_drop")

        # Also drop ENUM types left behind by SQLAlchemy
        with conn.cursor() as cur:
            cur.execute(
                "SELECT typname FROM pg_type WHERE typtype='e' AND typnamespace="
                "(SELECT oid FROM pg_namespace WHERE nspname='public');"
            )
            enums = [row[0] for row in cur.fetchall()]
            for enum_name in enums:
                cur.execute(f'DROP TYPE IF EXISTS "{enum_name}" CASCADE;')
            if enums:
                log.info("enum_types_dropped", count=len(enums))


def _run_alembic(alembic_url: str) -> None:
    """Run ``alembic upgrade head`` as a subprocess.

    Args:
        alembic_url: psycopg database URL passed via env var to Alembic.

    Raises:
        SystemExit: If Alembic exits with a non-zero code.
    """
    env = {**os.environ, "ALEMBIC_DB_URL": alembic_url}
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(PROJECT_ROOT),
        env=env,
    )
    if result.returncode != 0:
        print(f"ERROR: alembic upgrade head failed (exit {result.returncode})", file=sys.stderr)
        sys.exit(result.returncode)
    log.info("alembic_upgrade_complete")


# ─────────────────────────────────────────────────────────────────────────────
# Seed logic (async)
# ─────────────────────────────────────────────────────────────────────────────


async def _seed_payment_methods(session_maker: async_sessionmaker) -> None:  # type: ignore[type-arg]
    """Insert reference payment methods — idempotent (INSERT ON CONFLICT DO NOTHING).

    Args:
        session_maker: Configured async session factory.
    """
    async with session_maker() as session, session.begin():
        for name, currency, is_active in PAYMENT_METHODS:
            await session.execute(
                text(
                    "INSERT INTO payment_methods (name, currency, is_active) "
                    "VALUES (:name, :currency, :is_active) "
                    "ON CONFLICT (name) DO NOTHING"
                ),
                {"name": name, "currency": currency, "is_active": is_active},
            )
    log.info("payment_methods_seeded", count=len(PAYMENT_METHODS))


async def _seed_all(asyncpg_url: str) -> None:
    """Run all seed functions against the live database.

    Args:
        asyncpg_url: asyncpg connection URL for the async engine.
    """
    engine = create_async_engine(asyncpg_url, pool_pre_ping=True)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        await _seed_payment_methods(session_maker)
    finally:
        await engine.dispose()


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────


def main() -> None:
    """Entry point for the database initialization script.

    Parses CLI arguments, optionally resets the database, runs migrations,
    then seeds all reference data.
    """
    parser = argparse.ArgumentParser(
        description="P2P Bot — Database initialization (migrate + seed)"
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Drop all existing tables before migrating (IRREVERSIBLE).",
    )
    parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Skip confirmation prompt when using --reset.",
    )
    parser.add_argument(
        "--seed-only",
        action="store_true",
        help="Skip migrations; only run seed inserts (useful after manual migration).",
    )
    args = parser.parse_args()

    alembic_url = _get_alembic_url()
    asyncpg_url = _get_asyncpg_url()
    params = _parse_psql_params(alembic_url)

    print()
    print("╔══════════════════════════════════════════╗")
    print("║  P2P Bot — Database Initialization      ║")
    print("╚══════════════════════════════════════════╝")
    print(f"  DB Host : {params.get('host', '?')}:{params.get('port', '?')}")
    print(f"  DB Name : {params.get('dbname', '?')}")
    print(f"  DB User : {params.get('user', '?')}")
    print()

    # ── Reset ──────────────────────────────────────────────────────────────────
    if args.reset:
        if not args.yes:
            confirm = input(
                "⚠️  WARNING: --reset will DROP ALL TABLES and ALL DATA.\n"
                "   Type 'yes' to continue: "
            ).strip()
            if confirm.lower() != "yes":
                print("Aborted.")
                sys.exit(0)
        print("Dropping all tables...")
        _drop_all_tables(params)

    # ── Migrations ─────────────────────────────────────────────────────────────
    if not args.seed_only:
        # Drop stale alembic_version when schema is empty
        if not _table_exists(params, "users"):
            log.info("fresh_db_detected_resetting_alembic_version")
            _drop_all_tables(params)  # Cleans up any leftover alembic_version too

        print("Running alembic upgrade head...")
        _run_alembic(alembic_url)

    # ── Seed ───────────────────────────────────────────────────────────────────
    print("Seeding reference data...")
    asyncio.run(_seed_all(asyncpg_url))

    print()
    print("╔══════════════════════════════════════════╗")
    print("║  ✅  Database ready!                     ║")
    print("╚══════════════════════════════════════════╝")
    print()
    print("Seeded:")
    print(f"  • {len(PAYMENT_METHODS)} payment methods (RUB, UAH, KZT, USD, EUR, TRY, GBP)")
    print()
    print("Next steps:")
    print("  docker compose up -d --build")
    print("  docker compose logs -f bot")
    print()


if __name__ == "__main__":
    main()
