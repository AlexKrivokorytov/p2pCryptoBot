---
name: 🚀 Feature Request
about: Suggest a new feature or enhancement
title: "[FEAT] "
labels: enhancement
assignees: ''
---

## 🚀 Feature Description

<!-- A clear and concise description of what you want to happen -->

## 💡 Motivation

<!-- Why do you need this? What problem does it solve? -->

## 🏗️ Technical Scope

<!-- Answer the questions relevant to your request -->

**Which layer does this change touch?**
- [ ] `bot/handlers/` — Telegram UI
- [ ] `services/` — Business logic
- [ ] `providers/` — External APIs (Crypto Pay, blockchain, etc.)
- [ ] `db/models/` — Database schema (requires Alembic migration)
- [ ] `tasks/` — Background workers
- [ ] `api/` — FastAPI REST backend
- [ ] `frontend/` — React Mini App

**Does this require a database migration?**
- [ ] Yes — new table or column
- [ ] No

**Does this involve financial state mutations?**
- [ ] Yes — will need `SELECT ... FOR UPDATE` + idempotency key
- [ ] No

## 📐 Proposed API / UX Sketch

```
# Example: new command flow, API endpoint, or data model
```

## 🔗 Related Issues

<!-- Link any related issues or PRs -->
