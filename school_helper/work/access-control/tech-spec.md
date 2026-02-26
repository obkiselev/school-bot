---
created: 2026-02-26
status: draft
branch: dev
size: M
---

# Tech Spec: Access Control

## Solution

Add access control to the Telegram bot via aiogram outer middleware + SQLite-backed whitelist.

Every incoming `Message` and `CallbackQuery` passes through `AccessControlMiddleware` before reaching any handler. The middleware queries the `users` table for `role` and `is_blocked` columns. If the user is not in the whitelist or is blocked — the middleware responds with "❗ Доступ ограничен" and stops the update from reaching handlers.

Admin commands (`/allow`, `/block`, `/users`) are implemented as a new router registered before other routers. The middleware exempts admin commands from blocking (admins must always be able to manage access).

The primary admin is bootstrapped via `ADMIN_ID` in `.env`. Database migration adds `role` and `is_blocked` columns to the existing `users` table on startup.

## Architecture

### What we're building/modifying

- **AccessControlMiddleware** (`bot/middleware/access.py`) — outer middleware on Dispatcher level for both Message and CallbackQuery. Checks user access before any handler runs.
- **Admin handlers** (`bot/handlers/admin.py`) — new router with `/allow`, `/block`, `/users` commands. Only accessible to admin-role users.
- **Database migration** (`bot/db/database.py`) — idempotent `ALTER TABLE users ADD COLUMN role` and `ADD COLUMN is_blocked`. Sets ADMIN_ID user as admin on startup.
- **Access queries** (`bot/db/queries.py`) — new functions: `is_user_allowed()`, `set_user_access()`, `block_user()`, `get_all_users_list()`.
- **Config** (`bot/config.py`) — new `ADMIN_ID` env variable.
- **Dispatcher setup** (`run.py`) — register middleware and admin router.

### How it works

```
User sends message/clicks button
  → Dispatcher outer middleware (AccessControlMiddleware)
    → Query DB: SELECT role, is_blocked FROM users WHERE user_id = ?
    → User not found OR is_blocked = 1?
      → YES: respond "❗ Доступ ограничен", return (don't call handler)
      → NO: call handler normally
    → Special case: user is in active quiz (FSM state = answering_question)
      AND is_blocked = 1 → allow to finish current test
  → Handler processes the update normally
```

Admin command flow:
```
Admin sends /allow 123456789 student
  → AccessControlMiddleware passes (admin is allowed)
  → admin.router matches /allow command
  → Handler validates args, calls set_user_access(123456789, "student")
  → Responds with confirmation
```

## Decisions

### Decision 1: Middleware vs decorator-based access check
**Decision:** Outer middleware on Dispatcher level
**Rationale:** Intercepts ALL updates (messages + callbacks) in one place. No need to add decorators to every handler. Outer middleware runs before router filters, so even unmatched updates are blocked.
**Alternatives considered:** Per-handler decorator — rejected because it requires modifying every handler and is easy to forget on new handlers.

### Decision 2: ALTER TABLE vs new table for roles
**Decision:** ALTER TABLE ADD COLUMN on existing `users` table
**Rationale:** Simpler — no JOINs needed. The `users` table already tracks user_id, username, first_name. Adding `role` and `is_blocked` extends it naturally. `ensure_user()` already does upsert on this table.
**Alternatives considered:** Separate `allowed_users` table — rejected because it adds unnecessary complexity (JOINs, two tables to maintain) for a simple whitelist.

### Decision 3: ADMIN_ID (singular) in .env
**Decision:** Single `ADMIN_ID` in `.env` as bootstrap admin. Additional admins added via `/allow ID admin`.
**Rationale:** The bot is for one family — one primary admin is sufficient for bootstrap. Multiple admins are managed through bot commands stored in DB.
**Alternatives considered:** `ADMIN_IDS` (comma-separated list) — rejected as unnecessary complexity for a single-family bot.

### Decision 4: Soft block during active test
**Decision:** If user is blocked while in an active quiz (FSM state `answering_question`), allow them to finish the current test. Block on next action after test completion.
**Rationale:** Abruptly cutting a test mid-question is poor UX. The middleware checks FSM state and allows quiz-related actions to continue if the user is mid-test.
**Alternatives considered:** Hard block (immediate) — rejected per user requirement.

### Decision 5: No automated tests
**Decision:** Manual verification only
**Rationale:** Family project without CI/CD. No existing test infrastructure (no pytest, no tests/ directory). The access logic is simple (DB lookup). User will verify manually.
**Alternatives considered:** Adding pytest + unit tests — rejected by user as excessive for this project.

## Data Models

### users table (modified)

```sql
-- Existing columns:
user_id       INTEGER PRIMARY KEY  -- Telegram user ID
username      TEXT                  -- @username
first_name    TEXT                  -- Display name
created_at    TEXT DEFAULT (datetime('now'))
last_active   TEXT DEFAULT (datetime('now'))

-- New columns (added via ALTER TABLE):
role          TEXT DEFAULT 'student'    -- 'admin' | 'student'
is_blocked    INTEGER DEFAULT 0        -- 0 = active, 1 = blocked
```

### Migration (idempotent)

```sql
-- Run on every startup, safe to repeat:
ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'student';
-- (SQLite raises error if column exists — catch and ignore)
ALTER TABLE users ADD COLUMN is_blocked INTEGER DEFAULT 0;
-- Set bootstrap admin:
UPDATE users SET role = 'admin' WHERE user_id = ?;  -- ADMIN_ID from .env
```

## Dependencies

### New packages
None. All needed functionality is built into aiogram and aiosqlite.

### Using existing (from project)
- `aiogram.BaseMiddleware` — base class for access control middleware
- `aiosqlite` via `bot/db/database.py:get_db()` — DB queries in middleware
- `bot/config.py` — environment variable loading pattern
- `bot/db/queries.py` — query patterns (raw SQL, `get_db()` singleton)

## Testing Strategy

**Feature size:** M

### Unit tests
None — agreed with user. No test infrastructure in the project.

### Integration tests
None — same reason.

### E2E tests
None — manual verification via Telegram.

## Agent Verification Plan

**Source:** user-spec "Как проверить" section.

### Verification approach
The bot runs locally and requires Telegram interaction. Automated agent verification is not possible. All verification is manual by the user.

### Per-task verification
| Task | verify: | What to check |
|------|---------|--------------|
| 1 | bash | `python -c "from bot.db.database import ...;"` — migration runs without error |
| 2 | bash | `python -c "from bot.middleware.access import AccessControlMiddleware"` — import succeeds |
| 3 | bash | `python -c "from bot.handlers.admin import router"` — import succeeds |
| 4 | bash | `python -c "from bot.config import ADMIN_ID"` — config loads |

### Tools required
bash — for import verification. Full functional testing is manual via Telegram.

## Risks

| Risk | Mitigation |
|------|-----------|
| All admins blocked, no one can manage bot | ADMIN_ID from .env is permanently admin — cannot be blocked or demoted via bot commands |
| FSM state orphaned when user blocked mid-test | MemoryStorage clears on restart. Soft block allows test completion. |
| Migration breaks existing users | ALTER TABLE ADD COLUMN is non-destructive. Existing users get default values (student, not blocked). |
| Callback spinner hangs for blocked users | Middleware calls `callback.answer()` before returning to dismiss the spinner. |
| Admin commands used in group chats | Middleware and admin handlers check `message.chat.type == 'private'`. |

## Acceptance Criteria

Technical acceptance criteria (supplement user-spec AC1-AC14):

- [ ] TAC1: `AccessControlMiddleware` registered on both `dp.message` and `dp.callback_query` as outer middleware
- [ ] TAC2: Database migration is idempotent — multiple bot restarts don't cause errors
- [ ] TAC3: ADMIN_ID user is always set to role='admin', is_blocked=0 on every startup
- [ ] TAC4: Middleware checks FSM state before blocking — allows quiz completion for blocked users
- [ ] TAC5: `callback.answer()` called for blocked callback queries to dismiss spinner
- [ ] TAC6: Admin router registered before other routers in dispatcher
- [ ] TAC7: No new dependencies added to requirements.txt
- [ ] TAC8: `.env.example` updated with `ADMIN_ID=` entry

## Implementation Tasks

<!-- Tasks are brief scope descriptions. AC, TDD, and detailed steps are created during task-decomposition. -->

### Wave 1 (независимые)

#### Task 1: Database migration and access queries
- **Description:** Add `role` and `is_blocked` columns to `users` table with idempotent migration. Add query functions for access control (is_user_allowed, set_user_access, block_user, get_all_users_list). Bootstrap ADMIN_ID as admin on startup.
- **Skill:** code-writing
- **Reviewers:** code-reviewer, security-auditor
- **Verify:** bash — python import check, migration runs without error
- **Files to modify:** `bot/db/database.py`, `bot/db/queries.py`, `bot/config.py`, `.env`, `.env.example`
- **Files to read:** `bot/db/database.py`, `bot/db/queries.py`, `bot/config.py`

#### Task 2: Access control middleware
- **Description:** Create AccessControlMiddleware using aiogram BaseMiddleware. It checks every Message and CallbackQuery against the whitelist. Blocked/unknown users get "Доступ ограничен" response. Allows quiz completion for users blocked mid-test (checks FSM state).
- **Skill:** code-writing
- **Reviewers:** code-reviewer, security-auditor
- **Verify:** bash — python import check
- **Files to modify:** `bot/middleware/__init__.py` (new), `bot/middleware/access.py` (new), `run.py`
- **Files to read:** `run.py`, `bot/db/queries.py`, `bot/states/quiz_states.py`

### Wave 2 (зависит от Wave 1)

#### Task 3: Admin command handlers
- **Description:** Create admin router with `/allow`, `/block`, `/users` commands. Validate input, enforce protection rules (no self-block, no blocking ADMIN_ID), show usage hints on bad format. Only works in private chats for admin-role users.
- **Skill:** code-writing
- **Reviewers:** code-reviewer, security-auditor
- **Verify:** bash — python import check
- **Files to modify:** `bot/handlers/admin.py` (new), `run.py`
- **Files to read:** `bot/handlers/start.py`, `bot/db/queries.py`, `bot/config.py`

### Final Wave

#### Task 4: Pre-deploy QA
- **Description:** Acceptance testing: verify all acceptance criteria from user-spec (AC1-AC14) and tech-spec (TAC1-TAC8). Manual verification checklist for the user.
- **Skill:** pre-deploy-qa
- **Reviewers:** none
