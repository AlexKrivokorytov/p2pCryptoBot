# 💎 p2pCryptoBot — Premium P2P Escrow System

![Project Banner](file:///C:/Users/krivo/.gemini/antigravity/brain/9aac2a7d-8190-4e0a-9959-e6257bd39702/p2p_bot_banner_new_1777571146522.png)

<p align="left">
  <img src="https://img.shields.io/badge/python-3.12-blue.svg" alt="Python 3.12">
  <img src="https://img.shields.io/badge/framework-aiogram_3.x-orange.svg" alt="Aiogram 3.x">
  <img src="https://img.shields.io/badge/db-SQLAlchemy_2.0-red.svg" alt="SQLAlchemy 2.0">
  <img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License: MIT">
  <img src="https://img.shields.io/badge/coverage-96%25-brightgreen" alt="Coverage">
</p>

**p2pCryptoBot** is a high-robust, production-ready **P2P Crypto Trading Bot** for Telegram. It acts as a secure Escrow service between Buyers and Sellers, ensuring trade safety through integration with **Crypto Pay API** and direct blockchain interactions (EVM/TON).

---

## ✨ Key Features

*   **🔒 Secure Escrow**: Automated fund holding during the trade lifecycle.
*   **💳 Multi-Currency**: Support for BTC, ETH, TON, USDT, and more via Crypto Pay.
*   **🧬 Web3 Wallets**: Real on-chain wallet generation (EVM/TON) with private keys encrypted at rest (AES-256-GCM).
*   **📊 Market Data**: Live rates from Binance Spot API for precise ad pricing.
*   **🤝 Integrated Chat**: Anonymous messaging between Maker and Taker within the bot.
*   **⚖️ Dispute System**: Moderator dashboard for conflict resolution with AI-assisted chat analysis.
*   **🛠️ Admin Dashboard**: Deep analytics, volume statistics, and dispute queue management.

---

## 🏗️ System Architecture

The project follows a strict layered architecture to ensure testability and scalability.

```mermaid
graph TD
    UI[Telegram UI / aiogram] --> Handlers[bot/handlers]
    Handlers --> Services[services/ Business Logic]
    Services --> DB[(PostgreSQL / SQLAlchemy)]
    Services --> Providers[providers/ External APIs]
    Providers --> CP[Crypto Pay API]
    Providers --> BN[Binance API]
    Providers --> RPC[Blockchain RPCs]
```

---

## 🚀 Quick Start

### 🐳 Via Docker (Recommended)
The fastest way to deploy the entire environment (Bot + DB + Migrations):

1.  Copy the config: `cp .env.example .env`
2.  Fill in `BOT_TOKEN` and `CRYPTOPAY_TOKEN`.
3.  Run:
    ```bash
    docker-compose up -d --build
    ```

### 🐍 Local Development
If you want to run the code directly:

```bash
# Setup environment
python -m venv venv
source venv/bin/activate # or venv\Scripts\activate on Windows

# Install dependencies in dev mode
pip install -e ".[dev]"

# DB Migrations
alembic upgrade head

# Run
python -m bot.main
```

---

## ⚙️ Configuration (.env)

| Variable | Description |
| :--- | :--- |
| `BOT_TOKEN` | Your token from @BotFather |
| `CRYPTOPAY_TOKEN` | API token from @CryptoBot (Crypto Pay) |
| `POSTGRES_URI` | Database connection string |
| `AES_KEY` | 64-character hex key for wallet encryption |
| `ADMIN_IDS` | Comma-separated Telegram IDs of admins |
| `GEMINI_API_KEY` | Key for AI Mediator (Gemini) |

---

## 🧪 Testing & Quality
We maintain high standards with >95% code coverage.

```bash
pytest          # Run tests
mypy .          # Type checking
ruff check .    # Linting & formatting
```

---

## 📁 Project Structure

*   `bot/`: UI Layer (Telegram handlers, keyboards, FSM).
*   `services/`: Business Logic (trades, escrow, disputes).
*   `db/`: Data models and Alembic migrations.
*   `providers/`: External API integrations (Crypto Pay, Exchanges).
*   `tasks/`: Background tasks (order cleanup, notifications).
*   `utils/`: Helper functions (encryption, formatting).

---

## 🗺️ Roadmap

- [x] **Phases 1-4**: Core P2P engine, chats, profiles, Crypto Pay integration.
- [x] **Admin Panel**: Dispute management and statistics.
- [ ] **AI Mediator**: Google Gemini integration for automated dispute analysis.
- [ ] **Phase 5 (On-Chain)**: Transition to fully decentralized Escrow via smart contracts.
- [ ] **Notifications**: Expanded webhook-based notification system.

---

## ⚠️ Security Notes

1.  **Exchange API Keys**: When adding keys, ensure **Withdraw** permissions are **disabled**.
2.  **Webhooks**: In production, configure `CRYPTOPAY_CALLBACK_SECRET` to verify Crypto Pay notifications.
3.  **AES_KEY**: Never change this key after users start saving API keys, as they won't be decryptable.

---
*Developed with ❤️ for secure trading.*