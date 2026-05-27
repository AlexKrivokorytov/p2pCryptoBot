# Contributing to p2pCryptoBot

Thank you for your interest in contributing! This guide covers everything you need to know to make a clean, mergeable pull request.

---

## 📋 Table of Contents

1. [Development Setup](#-development-setup)
2. [Layer Architecture Rules](#️-layer-architecture-rules-non-negotiable)
3. [Commit Conventions](#-commit-conventions)
4. [Running the CI Gate Locally](#-running-the-ci-gate-locally)
5. [Test Markers Explained](#-test-markers-explained)
6. [Adding a New Feature — Checklist](#-adding-a-new-feature--checklist)

---

## 🔧 Development Setup

> **Note:** Use a virtual environment, not Docker, for local development. Docker is for production and integration tests.

```bash
# 1. Clone
git clone https://github.com/AlexKrivokorytov/p2pCryptoBot
cd p2pCryptoBot

# 2. Create virtual environment (Python 3.12 required)
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/Mac:
source .venv/bin/activate

# 3. Install with dev dependencies
pip install -e ".[dev]"

# 4. Set up environment
cp .env.example .env
# Edit .env with your test tokens

# 5. Run migrations (requires PostgreSQL)
alembic upgrade head

# 6. Run the bot
python -m bot.main
```

For integration tests, start the test database:

```bash
docker compose up postgres -d
python -m pytest -m integration
```

---

## 🏗️ Layer Architecture Rules (Non-Negotiable)

The codebase has **four layers** and data flows **strictly one-directionally**:

```
bot/handlers/  →  services/  →  providers/  →  db/
```

| Layer | Location | Can import from | Cannot import from |
|---|---|---|---|
| **Handlers** (UI) | `bot/handlers/` | `services/`, `bot/keyboards.py`, `bot/config.py` | `providers/`, `db/models/` directly |
| **Services** (Logic) | `services/` | `providers/`, `db/`, `utils/`, `bot/config.py` | `bot/handlers/`, `bot/keyboards.py` |
| **Providers** (External) | `providers/` | `utils/`, `bot/config.py` | `services/`, `bot/` |
| **DB** (Data) | `db/` | nothing | nothing |

**`bot/config.py`** is the only cross-cutting concern — it may be imported by all layers.

**Violation examples that block merge:**
- A service importing `from bot.keyboards import ...`
- A handler importing `from providers.wallet_provider import ...`
- A provider importing `from services.user_service import ...`

---

## 📝 Commit Conventions

We use [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <subject>

[optional body]
[optional footer]
```

| Type | When to use |
|---|---|
| `feat` | A new feature |
| `fix` | A bug fix |
| `refactor` | Code change that neither fixes a bug nor adds a feature |
| `test` | Adding or updating tests |
| `docs` | Documentation only changes |
| `chore` | Build process, tooling, or dependency updates |
| `perf` | Performance improvements |

**Rules:**
- Subject line: imperative mood, ≤ 72 chars, no trailing period
- Example: `feat(marketplace): add promo code percentage discount`
- One logical change per commit — don't bundle unrelated changes

---

## ✅ Running the CI Gate Locally

Run this before every push. The CI will reject the PR if any of these fail:

```bash
# 1. Linting + formatting
ruff check . --fix && ruff format .

# 2. Type checking (strict)
mypy --strict bot/ services/ providers/ utils/ tasks/ db/

# 3. Security scan
bandit -r bot/ services/ providers/ utils/ tasks/ -ll

# 4. Dependency audit
pip-audit

# 5. Tests (requires PostgreSQL running)
pytest --cov=bot --cov=services --cov=providers --cov=utils --cov=tasks --cov=db --cov-fail-under=90
```

Or run everything in Docker (matches CI exactly):

```bash
docker compose run --rm api python -m pytest --cov-fail-under=90
```

---

## 🧪 Test Markers Explained

Every test must be marked with exactly one of:

| Marker | When to use | DB required | Mocks |
|---|---|---|---|
| `unit` | Pure logic, no I/O | ❌ No | All external calls mocked |
| `contract` | Validates external API response shapes | ❌ No | Mocked HTTP responses |
| `integration` | Live PostgreSQL, tests DB locking / concurrency | ✅ Yes | Real DB, mock external APIs |
| `b2b` | End-to-end B2B flows (Stars/TON, bot spawning) | ✅ Yes | Mock Telegram payments |

Usage:
```python
pytestmark = pytest.mark.unit  # or integration, contract, b2b

@pytest.mark.asyncio
async def test_my_function() -> None:
    ...
```

Running specific markers:
```bash
pytest -m unit           # fast, no DB needed
pytest -m integration    # requires PostgreSQL
pytest -m "unit or contract"  # combine
```

---

## 📦 Adding a New Feature — Checklist

### New Handler

- [ ] Create file in `bot/handlers/<feature>.py`
- [ ] Register router in `bot/main.py`
- [ ] Only call `services/` — never `providers/` or `db/` directly
- [ ] Use `get_branding(license_id)` for all user-facing strings
- [ ] Add `pytestmark = pytest.mark.unit` tests in `tests/test_handlers_<feature>.py`

### New Service

- [ ] Create file in `services/<feature>_service.py`
- [ ] All methods are `@staticmethod async def`
- [ ] Acquire `SELECT ... FOR UPDATE` lock before any financial mutation
- [ ] Use `spend_id` (UUID) on every transfer call
- [ ] Add docstring with Args/Returns/Raises
- [ ] Add `pytestmark = pytest.mark.integration` tests

### New Provider (External API)

- [ ] Create class in `providers/<name>_provider.py`
- [ ] Config (URL, key) passed in `__init__`, not read from env in methods
- [ ] All network calls are async and raise specific exceptions on failure
- [ ] Add `pytestmark = pytest.mark.contract` tests validating API response shapes

### New DB Model

- [ ] Add model class in `db/models/<name>.py`
- [ ] Include in `db/models/base.py` imports
- [ ] Generate migration: `alembic revision --autogenerate -m "add <name> table"`
- [ ] Review generated migration before applying
- [ ] Financial models: use `Numeric`, not `Float`; add `spend_id: UUID` if they have transfers

---

## 🔐 Security Checklist (for every PR)

- [ ] No hardcoded secrets, API keys, or credentials anywhere
- [ ] No `print()` in production code paths (use `structlog`)
- [ ] No user-controlled input passed to `eval()`, `exec()`, `subprocess()`
- [ ] All SQL via SQLAlchemy ORM or parameterized queries
- [ ] Private keys / secrets are never logged, even at debug level
- [ ] `hmac.compare_digest` used for any secret comparison (never `==`)

---

## ❓ Questions?

Open an issue or reach out to the maintainer directly via Telegram.
