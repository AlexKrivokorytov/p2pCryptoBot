## Description

<!-- Describe what this PR changes and why -->

## Related Issue

Closes #<!-- issue number -->

## Type of Change

- [ ] 🐛 Bug fix
- [ ] ✨ New feature
- [ ] ♻️ Refactor
- [ ] 🧪 Tests only
- [ ] 📚 Documentation only
- [ ] 🔧 Chore / tooling

## PR Checklist

### Code Quality
- [ ] All new public functions have docstrings (Args, Returns, Raises)
- [ ] All new function parameters and return types are annotated
- [ ] No `print()` in production code — use `structlog`
- [ ] No hardcoded secrets, tokens, or credentials

### Architecture
- [ ] Changes respect the layer rules: `handlers → services → providers → db`
- [ ] No handler imports from `providers/` or `db/models/` directly
- [ ] No service imports from `bot/handlers/` or `bot/keyboards.py`

### Tests
- [ ] Tests added/updated for all changed logic
- [ ] Every error path has a corresponding test
- [ ] Test marker is correct (`unit` / `contract` / `integration` / `b2b`)
- [ ] Coverage does not drop below 90%

### Financial Safety (if applicable)
- [ ] `SELECT ... FOR UPDATE` added for any financial state mutation
- [ ] `spend_id` (UUID) used for any transfer call — idempotency guaranteed
- [ ] Financial amounts use `Decimal`, not `float`

### Database (if applicable)
- [ ] Alembic migration generated: `alembic revision --autogenerate -m "..."`
- [ ] Migration reviewed (not just raw autogenerate output)

### CI Gate
- [ ] `ruff check . --fix && ruff format .` — clean
- [ ] `mypy --strict bot/ services/ providers/ utils/ tasks/ db/` — clean
- [ ] `pytest --cov-fail-under=90` — passing
- [ ] `bandit -r . -ll` — 0 findings

### Documentation
- [ ] `CHANGELOG.md` updated under `[Unreleased]`
- [ ] `.env.example` updated if new environment variables were added
