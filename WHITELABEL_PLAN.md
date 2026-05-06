# WHITE-LABEL P2P ESCROW BOT — MODERN DEVELOPMENT ROADMAP (2026 EDITION)

> **For AI Agents:** This file is the single source of truth for transforming the existing P2P bot into a premium, sellable white-label product. Read this entire file before making any changes. Follow phases in strict chronological order. Never skip a phase. Each phase has a Definition of Done.

---

## PROJECT CONTEXT & CURRENT STATE

**What exists:** A solid backend foundation built with Python 3.12, aiogram 3.x, SQLAlchemy 2.0 async, and PostgreSQL 16.
- **Implemented:** Dynamic i18n localization (`aiogram-i18n`), User Reputation System, Ad Creation Wizard (FSM), P2P Marketplace Board, AI Dispute Mediator (Gemini), and core Escrow Service logic (pessimistic locking).
- **Missing:** The actual trade execution UI loop, Mini App frontend, Web3 escrow, and enterprise security checks.

**What it needs to become:** A top-tier white-label product featuring Telegram Mini Apps, Non-custodial Web3 Escrow, and Proactive AI Anti-Fraud, ready to be sold to communities and entrepreneurs.

---

## ARCHITECTURAL RULES — NEVER VIOLATE
- **Layered Architecture:** `handlers/` (UI) → `services/` (Business Logic/DB) → `providers/` (External APIs).
- **No Direct DB Calls in Handlers:** Handlers only call `services/`.
- **Pessimistic Locking:** Every mutation of order status or balance MUST use `with_for_update()`.
- **Financial Safety:** All crypto transfers use stable `spend_id` (idempotency key).
- **Strict Typing:** Complete type hints, no bare `Any`.

---

## PHASE 1 — TRADE EXECUTION ENGINE (Finalizing MVP)
**Goal:** Connect the marketplace to the actual trading loop. Allow users to accept ads, lock escrow, chat, and release funds.

### 1.1 Trade Initiation (`bot/handlers/trade.py`)
- **Implement `trade:take_ad:{id}`:**
  1. Fetch the ad via `MarketplaceService`.
  2. Ask the user (Taker) how much fiat/crypto they want to trade (enforce `min_amount`/`max_amount` and Maker's balance).
  3. Create an `Order` via `OrderService.create_order()`.
  4. Generate a Crypto Pay invoice if the Taker is buying crypto, or lock from balance if selling.
  
### 1.2 P2P Chat Bridge
- Implement an anonymous message relay between Maker and Taker once an order is `pending_fiat`.
- Use a database table `TradeMessage` to log all messages for dispute resolution.
- Format: `[Buyer] Hello, I am sending the money.` -> Relayed to Seller anonymously.

### 1.3 Trade Lifecycle Actions
- **Buyer Action:** "I have paid (Fiat)" -> Updates order status, notifies Seller.
- **Seller Action:** "Confirm Receipt & Release" -> Triggers `EscrowService.release_escrow()`, which calls `CryptoPay.transfer()`.
- **Dispute Action:** "Raise Dispute" -> Triggers `DisputeService.raise_dispute()` and calls the existing Gemini AI Mediator.

**Definition of Done:**
- [ ] `bot/handlers/trade.py` created and registered.
- [ ] Taker can accept an ad and specify amount.
- [ ] Maker and Taker can chat anonymously through the bot.
- [ ] Trade can be successfully completed and escrow released via Crypto Pay.
- [ ] Trade can be disputed and resolved by AI/Admin.

---

## PHASE 2 — TELEGRAM MINI APP (TMA) MODERNIZATION
**Goal:** Replace clunky inline keyboards with rich HTML5 Telegram Web Apps for a premium user experience.

### 2.1 Backend API for TMA (`api/routes.py`)
- Add an `aiohttp` sub-application in `bot/main.py` specifically for the Web App backend.
- **Auth:** Implement Telegram WebApp `initData` validation to securely authenticate API requests using HMAC-SHA256.

### 2.2 TMA Frontend (React/Vue)
- Create a `webapp/` directory in the repository.
- **Marketplace View:** A clean UI with advanced filters (Coin, Fiat, Payment Method) and real-time updates.
- **Ad Creation View:** A seamless form replacing the bot FSM, with immediate validation.
- **Admin Dashboard:** Visual charts for trading volume, active disputes, and user management.

### 2.3 Integration
- Update the Main Menu bot keyboard to launch the Web App: `WebAppInfo(url="https://yourdomain.com/app")`.

**Definition of Done:**
- [ ] `aiohttp` API serves JSON endpoints for ads and profile.
- [ ] `initData` authentication middleware implemented.
- [ ] React/Vue app builds static files served via Nginx/aiohttp.
- [ ] Users can browse ads and create ads via the TMA.

---

## PHASE 3 — NON-CUSTODIAL WEB3 ESCROW
**Goal:** Offer decentralized trust by integrating TON smart contracts alongside centralized Crypto Pay.

### 3.1 TON Connect Integration
- Integrate `@tonconnect/sdk` into the Mini App.
- Allow users to link Tonkeeper or MyTonWallet to their profile.

### 3.2 Smart Contract Escrow
- Deploy an escrow master contract on the TON blockchain.
- When an order is created, the bot generates a unique payload. The Maker sends TON to the contract with this payload.
- Upon fiat confirmation, the bot (acting as an oracle) signs a release message, allowing the Taker to withdraw the funds.

**Definition of Done:**
- [ ] TON Connect integrated in TMA.
- [ ] Database `Order` model updated to support `escrow_type` (`cryptopay` or `smart_contract`).
- [ ] Bot can verify on-chain transactions via `pytoniq` or TON API.
- [ ] Bot can sign and broadcast release transactions.

---

## PHASE 4 — PROACTIVE AI & ANTI-FRAUD SYSTEM
**Goal:** Prevent scams before they happen by analyzing trade behavior in real-time.

### 4.1 Real-Time Chat Analyzer
- Hook into the P2P Chat Bridge (from Phase 1).
- Feed batches of messages to a lightweight local LLM or Gemini.
- **Triggers:** Look for requests to "send outside the bot", phishing links, or "triangulation" keywords.
- Automatically flag the trade and warn the users if a scam pattern is detected.

### 4.2 Behavioral Scoring
- Track metrics: `time_to_release`, `cancellation_rate`, `dispute_loss_rate`.
- Assign an internal `Risk Score` to users. If risk exceeds a threshold, require Admin approval for their ads.

**Definition of Done:**
- [ ] Chat messages analyzed asynchronously without blocking message delivery.
- [ ] Bot automatically sends a warning message in chat if high risk is detected.
- [ ] User profiles display a dynamic "Trust Score" based on behavior.

---

## PHASE 5 — DYNAMIC PRICING & AUTO-HEDGING
**Goal:** Professional tools for high-volume merchants.

### 5.1 Floating Exchange Rates
- Integrate Binance API (`ccxt`) to fetch live spot prices.
- Update `Ad` model: add `price_type` (`fixed`, `floating`) and `margin_percent`.
- Calculate trade amounts dynamically at the moment the Taker accepts the ad.

### 5.2 Auto-Hedging (Optional Module)
- Allow Makers to provide Binance read/trade API keys.
- When a P2P sell order completes, automatically execute a market buy on Binance to replenish inventory and avoid volatility risk.

**Definition of Done:**
- [ ] Background task periodically updates floating ad prices.
- [ ] Takers see real-time calculated rates based on live Binance prices.
- [ ] Auto-hedging module implemented in `providers/exchange_provider.py`.

---

## PHASE 6 — ENTERPRISE SECURITY & DELIVERY PACKAGING
**Goal:** Ensure 0 vulnerabilities and package the codebase for easy white-label distribution.

### 6.1 Security Pipeline (`.github/workflows/ci.yml`)
- Implement strict CI/CD with 7 jobs: `lint`, `typecheck`, `test`, `bandit` (SAST), `safety` (dependencies), `trivy` (containers).
- Run automated contract tests against mock Crypto Pay and Binance APIs.

### 6.2 Setup Automation (`setup.sh`)
- Create an interactive bash script that provisions `.env`, generates secure `AES_KEY`s, and prompts for Bot Tokens.
- Automatically configure Nginx and Let's Encrypt SSL for the Web App webhook.

### 6.3 Final Polish
- Write a comprehensive `DEPLOY.md` for buyers.
- Strip all development artifacts.

**Definition of Done:**
- [ ] GitHub Actions CI passes with 100% success.
- [ ] `setup.sh` successfully deploys the full stack (Bot + DB + WebApp) on a fresh Ubuntu instance.
- [ ] Documentation is pristine and non-technical friendly.
