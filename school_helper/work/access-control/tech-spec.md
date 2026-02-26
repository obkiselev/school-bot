---
created: 2026-02-26
status: approved
branch: dev
size: M
---

# Tech Spec: Access Control

## Solution

Add access control to the Telegram bot via aiogram outer middleware + SQLite-backed whitelist.

Every incoming `Message` and `CallbackQuery` passes through `AccessControlMiddleware` before reaching any handler. The middleware queries the `users` table for `role` and `is_blocked` columns. If the user is not in the whitelist or is blocked — the middleware responds with "❗ Доступ ограничен" and stops the update from reaching handlers. No exceptions — admin commands are also blocked for non-whitelisted users. Only whitelisted admins can run `/allow`, `/block`, `/users`.

Additionally, the middleware always checks ADMIN_ID from `.env` first (before DB lookup) to guarantee the primary admin is never locked out even if the database is corrupted.

The primary admin is bootstrapped via `ADMIN_ID` in `.env`. Database migration adds `role` and `is_blocked` columns to the existing `users` table on startup. If ADMIN_ID is not yet in the `users` table, it is inserted automatically.

## Architecture

### What we're building/modifying

- **AccessControlMiddleware** (`bot/middleware/access.py`) — outer middleware on Dispatcher level for both Message and CallbackQuery. Checks user access before any handler runs. No exemptions for any commands.
- **Admin handlers** (`bot/handlers/admin.py`) — new router with `/allow`, `/block`, `/users` commands. Admin-role check is done inside the handler (double protection: middleware ensures user is whitelisted, handler checks role == admin).
- **Database migration** (`bot/db/database.py`) — idempotent `ALTER TABLE users ADD COLUMN role` and `ADD COLUMN is_blocked`. Inserts and sets ADMIN_ID user as admin on startup.
- **Access queries** (`bot/db/queries.py`) — new functions: `is_user_allowed()`, `set_user_access()`, `block_user()`, `get_all_users_list()`.
- **Config** (`bot/config.py`) — new `ADMIN_ID` env variable with startup validation.
- **Dispatcher setup** (`run.py`) — register middleware and admin router.

### How it works

```
User sends message/clicks button
  → Dispatcher outer middleware (AccessControlMiddleware)
    → Is user_id == ADMIN_ID from .env? → YES: always pass (short-circuit)
    → Query DB: SELECT role, is_blocked FROM users WHERE user_id = ?
    → User not found?
      → YES: respond "❗ Доступ ограничен", return
    → User is_blocked = 1?
      → Check FSM state: is user in QuizFlow.answering_question?
        → YES and action is quiz-related (ans:* callback or text answer): allow
        → Otherwise: respond "❗ Доступ ограничен", return
    → User found and not blocked: call handler normally
  → Handler processes the update
```

Admin command flow:
```
Admin sends /allow 123456789 student
  → AccessControlMiddleware: admin is whitelisted → passes
  → admin.router matches /allow command
  → Handler checks: is sender's role == 'admin'? YES
  → Validates args: user_id is numeric, role is in {'student', 'admin'}
  → Calls set_user_access(123456789, "student") — inserts or updates, sets is_blocked=0
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
**Decision:** If user is blocked while in an active quiz (FSM state `answering_question`), allow quiz-related actions only: `ans:*` callbacks and text answers. All other actions (start_test, my_results, go_home, etc.) are blocked immediately.
**Rationale:** Abruptly cutting a test mid-question is poor UX. The middleware checks FSM state AND the specific action type to limit the exemption scope.
**Alternatives considered:** Hard block (immediate) — rejected per user requirement. Full FSM state exemption (allow any action) — rejected because it would let blocked users navigate menus.

### Decision 5: No automated tests
**Decision:** Manual verification only
**Rationale:** Family project without CI/CD. No existing test infrastructure (no pytest, no tests/ directory). The access logic is simple (DB lookup). User will verify manually.
**Alternatives considered:** Adding pytest + unit tests — rejected by user as excessive for this project.

### Decision 6: DB failure mode — fail-closed
**Decision:** If the database query fails in the middleware, block the user (fail-closed).
**Rationale:** For a security control, failing open (allowing access on DB error) is worse than failing closed (blocking everyone). The ADMIN_ID short-circuit check happens before the DB query, so the primary admin can always access the bot to diagnose issues.
**Alternatives considered:** Fail-open — rejected because it defeats the purpose of access control.

### Decision 7: ADMIN_ID short-circuit in middleware
**Decision:** The middleware checks `user_id == ADMIN_ID` (from .env) before any DB lookup. If match — always allow, regardless of DB state.
**Rationale:** Prevents lockout if DB is corrupted, migration fails, or admin is accidentally modified in DB. Guarantees at least one user always has access.
**Alternatives considered:** DB-only check — rejected because a DB failure could lock out everyone.

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
-- Bootstrap admin — INSERT if not exists, then set role:
INSERT OR IGNORE INTO users (user_id, role, is_blocked) VALUES (?, 'admin', 0);
UPDATE users SET role = 'admin', is_blocked = 0 WHERE user_id = ?;
-- (ADMIN_ID from .env)
```

### Query functions

- `is_user_allowed(user_id) -> tuple[bool, str|None]` — returns (is_allowed, role). User is allowed if found AND is_blocked=0.
- `set_user_access(user_id, role='student') -> None` — INSERT OR REPLACE. Sets role and is_blocked=0 (unblocks if was blocked). Used by `/allow`.
- `block_user(user_id) -> bool` — SET is_blocked=1. Returns False if user not found.
- `get_all_users_list() -> list[dict]` — returns all users with user_id, first_name, username, role, is_blocked.

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
None — agreed with user. No test infrastructure in the project. Accepted risk: regressions in access logic will only be caught by manual testing.

### Integration tests
None — same reason.

### E2E tests
None — manual verification via Telegram.

## Agent Verification Plan

**Source:** user-spec "Как проверить" section.

### Verification approach
The bot runs locally and requires Telegram interaction. Full functional testing is manual by the user. Agent performs structural checks: imports, migration, config loading.

### Per-task verification
| Task | verify: | What to check |
|------|---------|--------------|
| 1 | bash | `python -c "from bot.db.database import get_db; from bot.db.queries import is_user_allowed, set_user_access, block_user, get_all_users_list; from bot.config import ADMIN_ID; print('OK')"` — all new functions exist and config loads |
| 2 | bash | `python -c "from bot.middleware.access import AccessControlMiddleware; print('OK')"` — middleware class exists |
| 3 | bash | `python -c "from bot.handlers.admin import router; print('OK')"` — admin router exists |

### Tools required
bash — for structural verification. Full functional testing is manual via Telegram.

### Manual verification checklist (user performs after all tasks)
- Write to bot from account NOT in whitelist → "Доступ ограничен"
- `/allow child_ID` from admin → confirmation message
- `/start` from child → normal main menu
- `/block child_ID` → block, then check new test cannot start
- Start a test, then `/block` from another account → child can finish current test
- `/users` → see list with names, roles, statuses
- `/block own_ID` → error "Нельзя заблокировать самого себя"
- `/block ADMIN_ID` from another admin → error "Нельзя заблокировать главного администратора"
- `/allow abc` → usage hint with correct format

## Risks

| Risk | Mitigation |
|------|-----------|
| All admins blocked, no one can manage bot | ADMIN_ID from .env is permanently admin via short-circuit check — cannot be blocked or demoted. Even if DB is corrupted, ADMIN_ID has access. |
| DB query fails in middleware | Fail-closed: block all users. ADMIN_ID short-circuit runs before DB query, so primary admin still has access. |
| FSM state orphaned when user blocked mid-test | MemoryStorage clears on restart. Soft block allows quiz completion (only quiz-related actions). |
| Migration breaks existing users | ALTER TABLE ADD COLUMN is non-destructive. Existing users get default values (student, not blocked). |
| Callback spinner hangs for blocked users | Middleware calls `callback.answer()` before returning to dismiss the spinner. |
| Admin commands used in group chats | Admin handlers check `message.chat.type == 'private'`. |
| ADMIN_ID not set or invalid in .env | Validate at startup: if ADMIN_ID is empty or non-numeric, log a warning. Bot still works but without access control enforcement. |
| ADMIN_ID not yet in users table on first run | INSERT OR IGNORE before UPDATE ensures the record exists. |

## Acceptance Criteria

Technical acceptance criteria (supplement user-spec AC1-AC14):

- [ ] TAC1: `AccessControlMiddleware` registered on both `dp.message` and `dp.callback_query` as outer middleware
- [ ] TAC2: Database migration is idempotent — multiple bot restarts don't cause errors
- [ ] TAC3: ADMIN_ID user is always set to role='admin', is_blocked=0 on every startup (INSERT OR IGNORE + UPDATE)
- [ ] TAC4: Middleware checks FSM state before blocking — allows only quiz-related actions (ans:* callbacks, text answers) for blocked users mid-test
- [ ] TAC5: `callback.answer()` called for blocked callback queries to dismiss spinner
- [ ] TAC6: Admin router registered before other routers in dispatcher
- [ ] TAC7: No new dependencies added to requirements.txt
- [ ] TAC8: `.env.example` updated with `ADMIN_ID=` entry
- [ ] TAC9: ADMIN_ID from .env is checked first in middleware (short-circuit, before DB query) — guarantees primary admin is never locked out
- [ ] TAC10: DB failure in middleware results in blocking (fail-closed), except for ADMIN_ID
- [ ] TAC11: `set_user_access()` both sets role AND sets is_blocked=0 (unblocks user)
- [ ] TAC12: Admin input validation: user_id must be numeric, role must be in {'student', 'admin'}

## Implementation Tasks

<!-- Tasks are brief scope descriptions. AC, TDD, and detailed steps are created during task-decomposition. -->

### Wave 1

#### Task 1: Database migration and access queries
- **Description:** Add `role` and `is_blocked` columns to `users` table with idempotent migration. Add query functions for access control (is_user_allowed, set_user_access, block_user, get_all_users_list). Bootstrap ADMIN_ID as admin on startup via INSERT OR IGNORE + UPDATE. Validate ADMIN_ID at startup.
- **Skill:** code-writing
- **Reviewers:** code-reviewer, security-auditor, test-reviewer
- **Verify:** bash — `python -c "from bot.db.database import get_db; from bot.db.queries import is_user_allowed, set_user_access, block_user, get_all_users_list; from bot.config import ADMIN_ID; print('OK')"`
- **Files to modify:** `bot/db/database.py`, `bot/db/queries.py`, `bot/config.py`, `.env`, `.env.example`
- **Files to read:** `bot/db/database.py`, `bot/db/queries.py`, `bot/config.py`

### Wave 2 (зависит от Wave 1)

#### Task 2: Access control middleware
- **Description:** Create AccessControlMiddleware using aiogram BaseMiddleware. Checks every Message and CallbackQuery against the whitelist. ADMIN_ID from .env is checked first (short-circuit). DB failures result in fail-closed (block). Blocked/unknown users get "Доступ ограничен". Allows quiz-related actions only for users blocked mid-test.
- **Skill:** code-writing
- **Reviewers:** code-reviewer, security-auditor, test-reviewer
- **Verify:** bash — `python -c "from bot.middleware.access import AccessControlMiddleware; print('OK')"`
- **Files to modify:** `bot/middleware/__init__.py` (new), `bot/middleware/access.py` (new), `run.py`
- **Files to read:** `run.py`, `bot/db/queries.py`, `bot/states/quiz_states.py`, `bot/config.py`

#### Task 3: Admin command handlers
- **Description:** Create admin router with `/allow`, `/block`, `/users` commands. Validate input (numeric ID, role in {student, admin}), enforce protection rules (no self-block, no blocking ADMIN_ID, admin can block other admins), show usage hints on bad format. Only works in private chats for admin-role users.
- **Skill:** code-writing
- **Reviewers:** code-reviewer, security-auditor, test-reviewer
- **Verify:** bash — `python -c "from bot.handlers.admin import router; print('OK')"`
- **Files to modify:** `bot/handlers/admin.py` (new), `run.py`
- **Files to read:** `bot/handlers/start.py`, `bot/db/queries.py`, `bot/config.py`

### Final Wave

#### Task 4: Pre-deploy QA
- **Description:** Acceptance testing: verify all acceptance criteria from user-spec (AC1-AC14) and tech-spec (TAC1-TAC12). Produce manual verification checklist for the user.
- **Skill:** pre-deploy-qa
- **Reviewers:** none
- **Files to read:** `work/access-control/user-spec.md`, `work/access-control/tech-spec.md`
