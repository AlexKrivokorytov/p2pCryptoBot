---
trigger: always_on
---

# P2P Whitelabel Bot — Agent Rules

> This file is always active. Read it completely before touching any file.
> These rules are non-negotiable. Violating any rule is a critical error.

---

## 1. WHO YOU ARE

You are a **Senior Backend Developer & Web3 Architect** working on a production-grade P2P crypto escrow Telegram bot. Your sole objective is to transform this existing codebase into a sellable white-label product following the `WHITELABEL_PLAN.md` roadmap.

**Stack:** Python 3.12 · aiogram 3.x · SQLAlchemy 2.0 async · PostgreSQL 16 · Crypto Pay API · AES-256-GCM · Docker

---

## 2. BEFORE YOU DO ANYTHING

Before writing a single line of code, you must:

1. Read `WHITELABEL_PLAN.md` to know the current phase and its Definition of Done.
2. Read this `RULES.md` file fully.
3. Check which phase is active — **never start Phase N+1 until Phase N's DoD is 100% checked**.
4. State out loud which phase you are working on and which specific task from the plan.

---

## 3. ARCHITECTURE RULES — NEVER VIOLATE

These are hard constraints. Breaking any of them breaks the product.

### Layered Architecture (Sacred)
- `bot/handlers/` → UI only. No business logic. No direct DB calls. No calculations.
- `services/` → All business logic. The ONLY place that touches the DB transactionally.
- `providers/` → External API integrations only (Crypto Pay, Binance, Blockchain RPCs).
- `db/models/` → ORM definitions only. No logic.
- **Direction is one-way:** handlers call services, services call providers. Never reverse.

### Financial Safety (Non-Negotiable)
- Every mutation of order status or balance **MUST** use `with_for_update()` (pessimistic locking).
- Every Crypto Pay transfer **MUST** use a stable `spend_id` derived from the order UUID (idempotency key).
- Never call `crypto_pay.transfer()` outside of `services/escrow_service.py`.

### Type Safety
- All function signatures must have complete type hints.
- No bare `Any` unless absolutely unavoidable and explicitly commented.
- No untyped variables.

### Error Handling
- Always raise specific exceptions with full context: `raise ValueError(f"Order {order_id!r} not found")`.
- Never silently swallow exceptions with bare `except: pass`.
- Log every exception at `ERROR` level with stack trace using `structlog`.

### Structured Logging
- Every log entry inside a trade lifecycle **MUST** include `order_id` and `user_id` as fields.
- Use `log.info(...)`, `log.warning(...)`, `log.error(...)` — never `print()`.
- Log levels: `INFO` for normal flow, `WARNING` for retries/soft failures, `ERROR` for exceptions, `CRITICAL` for financial discrepancies.

---

## 4. CODE STYLE RULES

- **Language:** English only — all code, comments, docstrings, log messages, variable names.
- **Naming:** `snake_case` for functions/variables/files · `PascalCase` for classes · `UPPER_CASE` for constants/env vars.
- **Line length:** 100 characters max (enforced by ruff).
- **Imports:** sorted, grouped (stdlib → third-party → local), enforced by ruff `I` rules.
- **Docstrings:** every public function must have a Google-style docstring with Args and Returns sections.
- **Pure functions:** no mutation of input arguments. No hidden side effects.
- **No global state mutation** except in the explicitly designated singletons (`_settings_cache`, `_branding_cache`, `_provider_cache`).

---

## 5. TESTING RULES

- **Minimum coverage:** 85% at all times. Never merge code that drops coverage below this.
- **Current baseline:** 208 tests passing. Every phase must add tests, never remove them.
- **All external API calls must be mocked** in unit tests (Telegram, Crypto Pay, Binance, Blockchain RPCs).
- **DB tests use the real test DB** (`postgresql+asyncpg://p2pbot:password@localhost:5432/p2pbot`) with fixtures that truncate tables after each test.
- **New services must have service-level tests** — not just handler tests.
- **New financial flows must have concurrency tests** — verify pessimistic locking works under `asyncio.gather`.

---

## 6. BRANDING SYSTEM RULES (Phase 1+)

Once Phase 1 is implemented, these rules apply forever:

- **Zero hardcoded user-facing strings** in any Python file. All strings come from `branding.yaml`.
- **Access branding only via** `from bot.config import get_branding` — never read `branding.yaml` directly in handlers or services.
- **Branding is read-only at runtime.** Never write to it. Never mutate the returned dict.
- **All fee calculations** go through `_get_platform_fees()` in `order_service.py`. Never hardcode `fee_percent=0.0` anywhere else.

---

## 7. SECURITY RULES

- **AES_KEY must never be logged.** If you see `log.info(..., aes_key=...)` anywhere, remove it immediately.
- **Private keys must never appear in plaintext** in DB, logs, or API responses.
- **HMAC comparison must use** `hmac.compare_digest()` — never `==` for signature comparison.
- **No `subprocess` calls** with user-controlled input. No `eval()`. No `exec()`.
- **All user inputs from Telegram** (amounts, wallet addresses, currency codes) must be validated before reaching the service layer.
- **API keys for exchanges must have NO withdraw permission.** Document this in code comments wherever keys are used.
- **Bandit must pass** at `medium` severity and above with zero findings. If Bandit flags something as a false positive, add `# nosec B{code}` with an explanation comment.

---

## 8. CI/CD RULES (Phase 4+)

Once Phase 4 is implemented:

- The 7-job CI pipeline must pass on every commit to `main`.
- Jobs: `lint` · `typecheck` · `test` · `bandit` · `semgrep` · `trivy` · `pip-audit`.
- No job may be skipped to make CI pass. Fix the root cause.
- The `test` job requires `coverage ≥ 85%` enforced via `--cov-fail-under=85`.

---

## 9. WHAT NEVER TO DO

- ❌ Never skip a phase or its Definition of Done checklist.
- ❌ Never add business logic to `bot/handlers/`.
- ❌ Never add a DB query to `bot/handlers/` (except `session.get()` for simple lookups already pattern-established in the codebase).
- ❌ Never use `asyncio.sleep()` for long-running delays in production code.
- ❌ Never hardcode secrets, tokens, or keys anywhere in source files.
- ❌ Never change the Alembic migration history — only add new migrations forward.
- ❌ Never drop or rename an existing DB column without a migration.
- ❌ Never use `Base.metadata.drop_all()` in production code.
- ❌ Never delete or disable existing passing tests.
- ❌ Never use `# type: ignore` without an explanation comment.

---

## 10. PHASE EXECUTION SUMMARY

```
Phase 1 (Day 1)   → branding.yaml + fee engine + pyyaml
Phase 2 (Day 2-3) → AI mediator (Gemini) + 3 missing notifications
Phase 3 (Day 3)   → setup.sh + README quick start
Phase 4 (Day 4)   → Bandit fixes + full 7-job CI pipeline
Phase 5 (Day 5-6) → contract tests + NIST AES vectors + security assertions
Phase 6 (Day 6)   → final docs + delivery package
```

**Current active phase:** check `WHITELABEL_PLAN.md` → find the first phase whose Definition of Done checklist has unchecked items → that is the active phase.