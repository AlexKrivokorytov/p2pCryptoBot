# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased] — Phase 3–5 (B2B SaaS Marketplace)

### Added

#### Platform
- **React Mini App** frontend (Vite + TypeScript) for marketplace browsing, seller dashboard, and deal management
- **FastAPI REST backend** with JWT authentication, serving the Mini App and processing webhooks
- **Multi-bot SaaS management** via `BotSpawner` service — one master bot that spawns and manages white-label child bots

#### Marketplace & E-commerce
- **Digital Marketplace** — sellers can list digital goods (keys, files, access codes) for sale
- **Telegram Stars payments** — instant payment flow for digital goods with auto-delivery
- **TON native payments** — on-chain escrow for crypto deals with automatic monitoring
- **Promo code system** — percentage and fixed discounts, max-uses limit, expiry dates
- **Product image upload** — multipart upload with `python-magic` file type validation
- **Secure digital delivery** — HMAC-protected download links after payment confirmation
- **On-chain payout worker** — automatic fund release to seller wallet after deal completion

#### Financial
- **TON Scanner** — on-chain invoice monitoring via LiteClient (`pytoniq`)
- **Marketplace Scanner** — promotion expiry automation
- **Referral rewards system** — 20% of platform fee distributed to referrer on deal completion
- **Automated payout worker** (`tasks/payout_worker.py`) — fire-and-forget EVM/TON fund release

#### B2B
- **B2B License management** — purchase, activate, and manage white-label licenses
- **Stars-based self-service license purchase** — clients buy access directly in the bot
- **Per-client branding** — `get_branding(license_id)` returns client-specific config
- **Client bot instance registry** — `ClientBotInstance` model tracks managed bots

#### Quality
- **480+ automated tests** across `unit`, `contract`, `integration`, `b2b` markers
- **≥ 90% code coverage** enforced in CI
- `mypy --strict` clean across all 100+ source files
- `ruff` linting + formatting enforced pre-commit

---

## [1.0.0] — 2026-05

### Added

#### Core P2P Engine (Phase 1)
- **Order lifecycle** — `open → escrow_held → completed / cancelled / disputed`
- **Crypto Pay API integration** — invoice creation, HMAC webhook verification, fund transfer
- **Pessimistic DB locking** — `SELECT ... FOR UPDATE` on every financial state mutation
- **Idempotency keys** — `spend_id` (UUID) on every Crypto Pay transfer call
- **Concurrent order protection** — tested: 3 simultaneous takers, exactly 1 wins
- **Self-deal prevention** — maker cannot take their own order

#### Security & Encryption (Phase 1-2)
- **AES-256-GCM encryption** for private keys — validated against NIST SP 800-38D test vectors
- **HMAC-SHA256 webhook verification** using `hmac.compare_digest` (timing-attack resistant)
- **96-bit random nonce** per encryption — nonce reuse impossibility tested (100-sample)
- **License key protection** — HMAC-SHA256 key bound to Telegram Bot Token

#### Platform Features (Phase 2)
- **Admin Dashboard** — dispute queue, platform statistics, volume analytics, moderator actions
- **Dispute system** — moderator-mediated conflict resolution with resolution logging
- **Anonymous Maker-Taker chat** — in-bot messaging between trade parties
- **User profiles** — trade history, reputation, referral links
- **Full lifecycle push notifications** — taker found, fiat sent, escrow released, dispute, expiry
- **White-label branding** — zero-Python customization via `branding.yaml`

#### Infrastructure (Phase 1-2)
- **Multi-chain wallet generation** — EVM (secp256k1), TON (ed25519), Solana, Tron
- **Live exchange rates** — Binance Spot API adapter (with OKX/Bybit fallbacks)
- **One-command Docker deploy** — `docker compose up --build`
- **Guided setup wizard** — `setup.sh` (collects tokens, generates AES_KEY, creates `.env`)
- **Alembic migrations** — version-controlled schema evolution
- **266 automated tests** at initial release — ≥ 85% coverage
