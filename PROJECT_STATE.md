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

We have successfully implemented **Phases 1 through 4**, plus an Admin moderation panel.

1. **Core P2P Engine:** Ad creation, taking orders, and secure escrow state machine (`pending` -> `escrow_held` -> `completed` / `dispute`).
2. **Trade Chat & Profiles:** Anonymous message routing between Maker and Taker. User statistics (volume, successful trades).
3. **Web3 Wallets Generation:** Users can generate real non-custodial EVM (BSC/ETH) and TON wallets. Private keys are securely encrypted at rest using `AES-256-GCM`.
4. **Market Data & Balances:** 
   - `balance_service.py` aggregates real-time on-chain balances via `web3.py` and `Toncenter`.
   - `rate_service.py` fetches live market rates from Binance Spot API for P2P ad pricing suggestions.
5. **Admin Dashboard:** `/admin`, `/stats`, `/disputes`. Moderators can view platform volume, browse the dispute queue, and resolve conflicts via inline buttons.
6. **Deployment:** Dockerized architecture. The `migrate.sh` script automatically handles Alembic DB migrations safely on startup.

---

## 3. Where We Stopped

- **Admin Dashboard Completed:** The admin functionality was fully implemented and covered by tests.
- **Docker Fix:** Fixed an issue where the DB migrations (`alembic`) wouldn't run properly on a freshly recreated Docker volume. The bot now successfully starts from scratch using `docker-compose up -d`.
- **Clean up:** Removed outdated handover guides and temporary test output files.

---

## 4. What Remains to be Done (Roadmap)

When returning to the project, the following features are the next highest priorities:

### 🔴 Priority 1: AI Mediator (Gemini Integration)
In `services/dispute_service.py`, the function `ai_mediator_suggest()` is currently a stub. 
**Goal:** Hook this up using the `google-generativeai` SDK. When a dispute is raised, the AI should read the `Trade Chat` history and suggest a resolution (e.g., `taker_wins` or `maker_wins`) with reasoning to the Admin. 
*(Note: `GEMINI_API_KEY` is already present in `.env`).*

### 🟠 Priority 2: Expanded Notification System
In `services/notification_service.py`, we only have 2 notifications. We need to add:
- `notify_taker_escrow_released()` (inform the Taker they received the crypto).
- `notify_dispute_opened()` (inform both parties).
- `notify_order_expired()` (inform the Maker if their ad timed out).

### 🟡 Priority 3: True On-Chain Escrow (Phase 5)
Currently, the bot uses the centralized **Crypto Pay** API to hold escrow and transfer funds.
**Goal:** Transition to true non-custodial / self-hosted Web3 trading.
- Implement the `transfer()` logic in `EvmWalletProvider` and `TonWalletProvider`.
- Build raw transactions, sign them with the decrypted private keys, and broadcast them directly to the blockchain to release escrow to the Taker.

### 🟢 Priority 4: Fiat Rate Parsing for Local Currencies
Currently, `rate_service.py` fetches rates directly from Binance (e.g., `EURUSDT`). Currencies like `RUB`, `UAH`, or `KZT` are not natively traded against USDT on spot markets.
**Goal:** Integrate a secondary API (like an exchange rate API or specialized crypto-fiat aggregator) to show accurate prices for local fiat currencies.
