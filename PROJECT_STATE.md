# P2P Telegram Bot — Project State & Handover Guide

> **Important note for AI Models:** Read this file to understand the current architecture, what has been implemented, and what the next tasks are.

## 1. Project Overview & Architecture

This project is a highly robust, production-ready **P2P Crypto Trading Bot** in Telegram. It acts as an escrow service between a crypto Seller and a fiat Buyer (or vice versa).

**Tech Stack:**
- **Language**: Python 3.12
- **Framework**: `aiogram` (v3.27+)
- **Database**: PostgreSQL 16 via `SQLAlchemy 2.0` (async) and `Alembic`
- **Current Escrow Backend**: Crypto Pay API (by Telegram)
- **Testing**: `pytest` + `pytest-cov` (Currently 208/208 tests passing, ~87% coverage)

**Strict Layered Architecture:**
- `bot/handlers/`: UI layer. FSM, keyboards, and Telegram events. NO direct business logic.
- `services/`: Business layer (`order_service.py`, `dispute_service.py`, `balance_service.py`). Contains DB transactional logic (`with_for_update`).
- `db/models/`: SQLAlchemy ORM.
- `providers/`: External APIs (Crypto Pay, Binance Spot API, Web3/TON RPCs).
- `utils/`: Encryption (`AES-256-GCM`), formatting.

---

## 2. Current State: What is Done?

We have successfully implemented **Phases 1 through 5 (Foundations)**, plus an Admin moderation panel and B2B SaaS features.

1. **Core P2P Engine:** Ad creation, taking orders, and secure escrow state machine (`pending` -> `escrow_held` -> `completed` / `dispute`).
2. **Trade Chat & Profiles:** Anonymous message routing between Maker and Taker. User statistics (volume, successful trades).
3. **Web3 Wallets Generation:** Users can generate real non-custodial EVM (BSC/ETH) and TON wallets. Private keys are securely encrypted at rest using `AES-256-GCM`.
4. **Market Data & Balances:** 
   - `balance_service.py` aggregates real-time on-chain balances via `web3.py` and `Toncenter`.
   - `rate_service.py` fetches live market rates from Binance Spot API for P2P ad pricing suggestions.
5. **Admin Dashboard:** `/admin`, `/stats`, `/disputes`. Moderators can view platform volume, browse the dispute queue, and resolve conflicts via inline buttons.
6. **B2B SaaS Foundations:** 
   - **Telegram Stars**: Buy 1-year licenses with XTR.
   - **TON Payments**: Automated license activation via `TONScanner` monitoring the master wallet.
   - **Bot Spawning**: Create managed white-label bot instances via Telegram's Managed Bot API.
7. **Expanded Notification System:** Dynamic branding-based templates for all trade lifecycle events (disputes, releases, refunds, expiry).
8. **AI Removal:** Cleaned the project of all legacy AI/dispute mediation stubs and experimental features to focus on a robust "student-like" or "SaaS-ready" core.
9. **Multi-Chain Marketplace (Phase 8 Foundations):**
   - **On-Chain Escrow**: Marketplace deals now generate unique, non-custodial escrow wallets for EVM, TON, Solana, and Tron.
   - **Ecommerce Service**: Decoupled product and deal logic into `MarketplaceEcommerceService`.
   - **Automated Verification**: `MarketplaceScanner` monitors on-chain deposits to automatically mark deals as `paid`.
   - **Multi-Chain Checkout**: Frontend updated to display blockchain-specific payment instructions and address copy-to-clipboard.

---

## 3. Where We Stopped

- **Marketplace Multi-Chain Foundations Completed:** Expanded DB schema, refactored service/API layers, implemented background scanners, and updated the checkout UI to support decentralized crypto payments for digital/physical goods.
- **Task Verification:** Database migrations applied. Service layer and scanners implemented. `Checkout.tsx` and `ProductDetails.tsx` updated.

---

## 4. What Remains to be Done (Roadmap)

The following features are the next highest priorities for the project:

### 🟠 Priority 1: True On-Chain Escrow (Phase 6)
Transition from centralized `Crypto Pay` to decentralized, self-hosted Web3 trading.
- Implement `transfer()` in `EvmWalletProvider` (Web3.py) and `TonWalletProvider` (Pytoniq).
- Sign and broadcast transactions using decrypted user private keys to release escrow.
- Monitor generated user wallets for incoming "Trade Funding" transactions.

### 🟡 Priority 2: Fiat Rate Parsing for Local Currencies
Integrate a secondary API (like `CurrencyAPI` or `ExchangeRate-API`) to show accurate prices for `RUB`, `UAH`, `KZT`, etc., which are missing from Binance's direct spot pairs.

### 🟢 Priority 3: B2B License Management & Refunds
- Add administrative tools to manually revoke or extend B2B licenses.
- Implement `refundStarPayment` in `bot/handlers/admin.py` to allow moderators to process Stars refunds.
- Expand `branding.yaml` validation for custom bot instances.
