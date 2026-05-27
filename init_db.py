"""One-shot database initializer for P2P Marketplace Bot.

Replaces Alembic migrations for clean deploys. Creates all tables + ENUM types
in the correct dependency order via raw SQL, then seeds essential reference data.

Usage::

    python init_db.py            # create schema + seed
    python init_db.py --drop     # ⚠ drop ALL tables first, then recreate
    python init_db.py --dry-run  # show SQL plan, make no changes

Why raw SQL for ENUMs?
    asyncpg fails silently when SQLAlchemy tries to emit CREATE TYPE inside a
    transaction that already opened. Emitting them explicitly (IF NOT EXISTS)
    before ``create_all`` avoids this bug completely.

Future-proofing:
    This file is structured in labelled sections. When you add a new ENUM or
    seed dataset, add it in the matching section — the order is deliberate.
"""

from __future__ import annotations

import argparse
import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import structlog
from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

load_dotenv()

from bot.config import settings  # noqa: E402  (must be after load_dotenv)

# ── Import ALL models so that Base.metadata is fully populated ────────────────
# Order matters: base types first, then dependents.
from db.models.admin import AdminAuditLog  # noqa: F401 E402
from db.models.b2b import B2BLicense, TONInvoice  # noqa: F401 E402
from db.models.base import Base  # noqa: E402
from db.models.chat import ChatMessage  # noqa: F401 E402
from db.models.marketplace import (  # noqa: F401 E402
    Ad,
    DisputeTicket,
    PaymentMethod,
    ReferralReward,
    Review,
    UserPaymentDetail,
)
from db.models.notification import InAppNotification  # noqa: F401 E402
from db.models.order import Order  # noqa: F401 E402
from db.models.product import MarketplaceDeal, Product, ProductReview, PromoCode  # noqa: F401 E402
from db.models.user import User  # noqa: F401 E402
from db.models.wallet import UserWallet  # noqa: F401 E402

log = structlog.get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Section 1 — ENUM types
# All Postgres ENUM types that SQLAlchemy models reference.
# Add new ENUMs here when you add a new StrEnum to any model.
# ─────────────────────────────────────────────────────────────────────────────

_ENUM_DEFINITIONS: list[tuple[str, list[str]]] = [
    # (type_name, [values...])
    # P2P escrow orders
    ("order_type", ["sell_crypto", "buy_crypto"]),
    (
        "order_status",
        [
            "pending_funding",
            "active",
            "escrow_held",
            "completed",
            "dispute",
            "cancelled",
        ],
    ),
    ("supported_asset", ["BTC", "TON", "USDT", "USDC", "ETH", "SOL", "TRX"]),
    # On-chain wallets
    ("wallet_chain", ["ton", "evm", "solana", "tron"]),
    # Marketplace ads
    ("ad_type", ["buy", "sell"]),
    ("price_type", ["fixed", "floating"]),
    # Marketplace products & deals
    ("product_currency_type", ["XTR", "FIAT", "CRYPTO"]),
    ("deal_currency_type", ["XTR", "FIAT", "CRYPTO"]),
    (
        "deal_status",
        [
            "created",
            "paid",
            "delivered",
            "completed",
            "dispute",
            "cancelled",
        ],
    ),
    ("promo_discount_type", ["percentage", "fixed"]),
    # ── Future ENUMs — add here as the marketplace grows ─────────────────────
    # ("subscription_tier", ["free", "basic", "pro", "enterprise"]),
    # ("payout_method", ["crypto_pay", "ton", "lightning", "bank"]),
    # ("kyc_level", ["none", "basic", "full"]),
    # ("campaign_type", ["flash_sale", "bundle", "loyalty"]),
]


async def _create_enums(conn: AsyncConnection) -> None:
    """Create all PostgreSQL ENUM types idempotently via DO $$ ... $$ blocks.

    asyncpg does not support CREATE TYPE IF NOT EXISTS inside a transaction.
    The DO block approach (checking pg_type) is the correct workaround.
    """
    for type_name, values in _ENUM_DEFINITIONS:
        quoted = ", ".join(f"'{v}'" for v in values)
        # language=SQL
        await conn.execute(
            text(
                f"""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_type WHERE typname = '{type_name}'
                    ) THEN
                        CREATE TYPE {type_name} AS ENUM ({quoted});
                    END IF;
                END
                $$;
                """
            )
        )
    log.info("enums_created", count=len(_ENUM_DEFINITIONS))


# ─────────────────────────────────────────────────────────────────────────────
# Section 2 — Table creation
# SQLAlchemy's create_all handles dependency order via FK analysis.
# ─────────────────────────────────────────────────────────────────────────────


async def _create_tables(conn: AsyncConnection) -> None:
    """Create all tables from ORM metadata. Idempotent (checkfirst=True)."""
    await conn.run_sync(Base.metadata.create_all, checkfirst=True)
    log.info("tables_created", count=len(Base.metadata.tables))


# ─────────────────────────────────────────────────────────────────────────────
# Section 3 — Extra indexes
# Any composite, partial, or expression indexes that SQLAlchemy can't emit
# from the ORM (i.e. not trivially expressed as Index() in the model).
# ─────────────────────────────────────────────────────────────────────────────

_EXTRA_INDEXES: list[str] = [
    # Active orders by asset — used by order-book queries
    """
    CREATE INDEX IF NOT EXISTS ix_orders_asset_status
    ON orders (asset, status)
    WHERE status IN ('active', 'escrow_held')
    """,
    # Active products by currency — used by marketplace browse
    """
    CREATE INDEX IF NOT EXISTS ix_products_currency_active
    ON products (currency_type, is_active)
    WHERE is_active = true
    """,
    # Pending deals per buyer — used to enforce duplicate-deal guard
    """
    CREATE INDEX IF NOT EXISTS ix_marketplace_deals_buyer_status
    ON marketplace_deals (buyer_id, status)
    WHERE status IN ('created', 'paid', 'delivered')
    """,
    # Active promo codes lookup by code + seller
    """
    CREATE INDEX IF NOT EXISTS ix_promo_codes_code_seller
    ON promo_codes (code, seller_id)
    """,
    # Full-text search on product title (GIN) — future catalogue search
    """
    CREATE INDEX IF NOT EXISTS ix_products_title_fts
    ON products USING gin(to_tsvector('simple', title))
    """,
    # Pending TON invoices — used by scanner
    """
    CREATE INDEX IF NOT EXISTS ix_ton_invoices_status_created
    ON ton_invoices (status, created_at)
    WHERE status = 'pending'
    """,
    # ── Future indexes — add here ─────────────────────────────────────────────
    # Geospatial index when adding seller location (PostGIS):
    # CREATE INDEX IF NOT EXISTS ix_users_location ON users USING gist(location)
    # Promoted products sorted by expiry:
    # CREATE INDEX IF NOT EXISTS ix_products_promoted ON products (promoted_until DESC) WHERE is_promoted = true
]


async def _create_indexes(conn: AsyncConnection) -> None:
    """Create all extra indexes idempotently."""
    for ddl in _EXTRA_INDEXES:
        await conn.execute(text(ddl.strip()))
    log.info("indexes_created", count=len(_EXTRA_INDEXES))


# ─────────────────────────────────────────────────────────────────────────────
# Section 4 — Seed data
# Reference data that must exist for the application to function correctly.
# All seeds use INSERT ... ON CONFLICT DO NOTHING — safe to re-run.
# ─────────────────────────────────────────────────────────────────────────────

# 4a — Payment methods
# These are the canonical payment methods shown in the P2P order book.
# Add new ones here as you expand to new markets/currencies.
_PAYMENT_METHODS: list[dict[str, str]] = [
    # ── Russian / CIS ────────────────────────────────────────────────────────
    {"name": "Сбербанк", "currency": "RUB"},
    {"name": "Тинькофф", "currency": "RUB"},
    {"name": "Альфа-Банк", "currency": "RUB"},
    {"name": "Т-Банк", "currency": "RUB"},
    {"name": "Газпромбанк", "currency": "RUB"},
    {"name": "ВТБ", "currency": "RUB"},
    {"name": "СБП (быстрые платежи)", "currency": "RUB"},
    {"name": "QIWI", "currency": "RUB"},
    {"name": "ЮMoney", "currency": "RUB"},
    {"name": "Kaspi", "currency": "KZT"},
    {"name": "monobank", "currency": "UAH"},
    {"name": "PrivatBank", "currency": "UAH"},
    # ── European ─────────────────────────────────────────────────────────────
    {"name": "Revolut", "currency": "EUR"},
    {"name": "Wise", "currency": "EUR"},
    {"name": "SEPA Transfer", "currency": "EUR"},
    {"name": "Paysera", "currency": "EUR"},
    # ── Global ───────────────────────────────────────────────────────────────
    {"name": "PayPal", "currency": "USD"},
    {"name": "Venmo", "currency": "USD"},
    {"name": "Cash App", "currency": "USD"},
    {"name": "Zelle", "currency": "USD"},
    {"name": "Bank Transfer", "currency": "USD"},
    {"name": "SWIFT", "currency": "USD"},
    # ── Asian ────────────────────────────────────────────────────────────────
    {"name": "WeChat Pay", "currency": "CNY"},
    {"name": "Alipay", "currency": "CNY"},
    {"name": "Paytm", "currency": "INR"},
    {"name": "UPI", "currency": "INR"},
    {"name": "PromptPay", "currency": "THB"},
    # ── Middle East / Africa ──────────────────────────────────────────────────
    {"name": "M-Pesa", "currency": "KES"},
    {"name": "Binance Pay", "currency": "USD"},  # crypto-backed fiat
    # ── Future payment methods — add here ────────────────────────────────────
    # {"name": "Strike",        "currency": "USD"},  # Lightning
    # {"name": "GCash",         "currency": "PHP"},
]


async def _seed_payment_methods(session: AsyncSession) -> None:
    """Insert canonical payment methods, skip if already present."""
    from sqlalchemy import select

    existing_result = await session.execute(select(PaymentMethod.name))
    existing_names = {row[0] for row in existing_result.all()}

    new_methods = [
        PaymentMethod(name=m["name"], currency=m["currency"], is_active=True)
        for m in _PAYMENT_METHODS
        if m["name"] not in existing_names
    ]
    if new_methods:
        session.add_all(new_methods)
        log.info("payment_methods_seeded", count=len(new_methods))
    else:
        log.info("payment_methods_already_seeded")


# 4b — Master admin user
async def _seed_master_user(session: AsyncSession) -> User:
    """Return existing admin user or create one if absent."""
    from sqlalchemy import select

    first_admin_id = next(iter(settings.ADMIN_IDS), 1)
    result = await session.execute(select(User).where(User.telegram_id == first_admin_id))
    admin = result.scalar_one_or_none()
    if admin is None:
        admin = User(
            telegram_id=first_admin_id,
            username=settings.MASTER_BOT_USERNAME,
            first_name="Admin",
            is_verified=True,
            is_verified_seller=True,
        )
        session.add(admin)
        await session.flush()
        log.info("master_user_created", telegram_id=first_admin_id)
    else:
        log.info("master_user_already_exists", telegram_id=first_admin_id)
    return admin


# 4c — Master B2B license
async def _seed_master_license(session: AsyncSession, owner: User) -> None:
    """Create the perpetual master B2BLicense if none exists."""
    from sqlalchemy import select

    result = await session.execute(select(B2BLicense).limit(1))
    if result.scalar_one_or_none() is not None:
        log.info("master_license_already_exists")
        return

    license_ = B2BLicense(
        id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        owner_id=owner.telegram_id,
        telegram_payment_charge_id="INITIAL_FREE_LICENSE",
        expires_at=datetime.now(UTC) + timedelta(days=365 * 100),  # perpetual
        is_active=True,
        branding={
            "bot": {
                "name": "P2P Master Bot",
                "welcome_message": "👋 Welcome to the P2P Crypto Marketplace!",
                "help_text": "Use /start to begin trading.",
                "support_username": settings.MASTER_BOT_USERNAME,
            },
            "marketplace": {
                "fee_percent": "1.0",
                "min_order_usdt": str(settings.ORDER_MIN_AMOUNT_USDT),
                "max_order_usdt": str(settings.ORDER_MAX_AMOUNT_USDT),
                "referral_fee_percent": "0.5",
            },
        },
    )
    session.add(license_)
    log.info("master_license_created", license_id=str(license_.id))


# ─────────────────────────────────────────────────────────────────────────────
# Section 5 — Drop all (destructive, --drop flag only)
# ─────────────────────────────────────────────────────────────────────────────


async def _drop_all(conn: AsyncConnection) -> None:
    """Drop all tables and ENUM types. DESTRUCTIVE — use only in dev/test."""
    log.warning("dropping_all_tables_and_types")
    await conn.run_sync(Base.metadata.drop_all)
    for type_name, _ in reversed(_ENUM_DEFINITIONS):
        await conn.execute(text(f"DROP TYPE IF EXISTS {type_name} CASCADE"))
    log.warning("drop_complete")


# ─────────────────────────────────────────────────────────────────────────────
# Section 6 — Orchestration
# ─────────────────────────────────────────────────────────────────────────────


async def init_db(*, drop_first: bool = False, dry_run: bool = False) -> None:
    """Initialize the database schema and seed essential data.

    Args:
        drop_first: If True, drop all tables before recreating. DESTRUCTIVE.
        dry_run: If True, log the plan and exit without making DB changes.
    """
    db_host = settings.POSTGRES_URI.split("@")[-1]
    log.info("db_init_start", uri=db_host, drop_first=drop_first, dry_run=dry_run)

    if dry_run:
        log.info(
            "dry_run_plan",
            enums=len(_ENUM_DEFINITIONS),
            tables=len(Base.metadata.tables),
            indexes=len(_EXTRA_INDEXES),
            payment_methods=len(_PAYMENT_METHODS),
        )
        log.info("dry_run_done — no changes made")
        return

    engine = create_async_engine(
        settings.POSTGRES_URI,
        echo=False,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
    )

    try:
        async with engine.begin() as conn:
            if drop_first:
                await _drop_all(conn)

            await _create_enums(conn)
            await _create_tables(conn)
            await _create_indexes(conn)

        session_pool = async_sessionmaker(engine, expire_on_commit=False)
        async with session_pool() as session, session.begin():
            await _seed_payment_methods(session)
            admin = await _seed_master_user(session)
            await _seed_master_license(session, admin)

    finally:
        await engine.dispose()

    log.info("db_init_complete", tables=len(Base.metadata.tables))


def _parse_args() -> argparse.Namespace:
    """Parse command-line arguments for init_db."""
    parser = argparse.ArgumentParser(
        description="Initialize the P2P Bot database schema and seed data."
    )
    parser.add_argument(
        "--drop",
        action="store_true",
        help="⚠ Drop ALL tables and re-create from scratch. Data will be lost.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making any DB changes.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    asyncio.run(init_db(drop_first=args.drop, dry_run=args.dry_run))
