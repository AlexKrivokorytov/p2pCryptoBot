---
trigger: always_on
---

P2P Bot Project: Engineering & DevOps Standards
1. Core Architecture Principles
Strict Layered Architecture:

bot/handlers/: UI/Telegram logic only. No business logic.

services/: Business logic and DB transactions.

providers/: External API/Blockchain interactions (Web3, TON, Binance).

db/models/: SQLAlchemy ORM definitions.

Naming Conventions:

camelCase for variables, functions, and method names (e.g., calculateEscrowFee).

PascalCase for class names (e.g., OrderService).

snake_case for file names and directory structures (e.g., order_service.py).

UPPER_CASE for environment variables and constants.

Async-First: All I/O operations must be non-blocking using asyncio and aiogram 3.x.

2. Security & Cryptography (Non-Custodial Focus)
Secret Management:

Never hard-code API keys or seeds. Use .env or Docker secrets.

Private keys must be encrypted at rest using AES-256-GCM.

Principle of Least Privilege: Database users and API keys (Alchemy, TON) must have the minimum required permissions.

Input Validation: Sanitize all user inputs from Telegram (amounts, wallet addresses) before processing.

No MPC: Logic relies on secure server-side signing with local encrypted keys.

3. Database & Concurrency
Integrity: Use SQLAlchemy 2.0 with asyncpg.

Race Condition Protection: Always use with_for_update() (pessimistic locking) in services/ when modifying user balances or order statuses.

Migrations: Use Alembic for all schema changes. Raw SQL in code is prohibited.

Isolation: Ensure proper transaction isolation levels for financial operations.

4. Blockchain & Web3 (Phase 5)
Reliability: Implement mandatory Transaction Simulation (via Alchemy traceCall or TON emulate) before broadcasting to the network.

Gas Optimization: Implement dynamic gas price fetching to prevent stuck transactions.

Raw Transactions: Build and sign transactions locally using web3.py (EVM) and TonSDK (TON).

Idempotency: Implement client_mutation_id or equivalent checks to prevent double-spending on retries.

5. Python & Quality Assurance
Type Safety: Use Type Hints for all function signatures and class members.

Testing:

Mandatory unit tests for services/ using pytest.

Use mocking for all external blockchain providers.

Maintain a minimum of 80% code coverage.

Clean Code: Follow DRY and KISS principles. Refactor dense logic into smaller, testable functions.

6. DevOps & Infrastructure
Containerization: Maintain a production-ready docker-compose.yml with health checks for all services.

Logging: Redirect stdout to structured logs. Separate errors (stderr) for alerting.

Automation: Use Bash scripts for bootstrapping (migrate.sh, setup_env.sh) with proper error handling (trap, set -e).

Observability: Implement basic health-check endpoints or logs for monitoring bot uptime and DB connectivity.

7. Error Handling & Resilience
Graceful Degradation: Use try/except blocks in providers/ with specific exception handling (e.g., RequestTimeout, InsufficientFunds).

Retries: Implement exponential backoff for external API calls.

Atomic Operations: Ensure that a failure in blockchain broadcasting does not leave the database in an inconsistent state (use commit/rollback blocks).