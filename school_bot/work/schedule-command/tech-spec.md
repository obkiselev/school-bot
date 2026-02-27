---
created: 2026-02-27
status: draft
branch: dev
size: M
---

# Tech Spec: Schedule Command (/raspisanie)

## Solution

Add `/raspisanie` command handler that fetches school schedule from MeSH API and displays it via inline keyboards. The existing `MeshClient.get_schedule()` method and `Lesson` model are used as-is. A token refresh helper is added to handle expired tokens transparently. Child selection and period switching use callback_data-encoded inline buttons (no FSM state), making them resilient to bot restarts.

## Architecture

### What we're building/modifying

- **`handlers/schedule.py`** — Command handler for `/raspisanie` and callback handlers for child selection, period switching, and retry. Core module.
- **`utils/token_manager.py`** — Helper to check token expiration and auto-refresh using stored credentials. Reusable across future commands.
- **`bot.py`** — Register schedule router.

### How it works

1. User sends `/raspisanie` → handler checks registration via `get_user()`.
2. If not registered → reply with "register first" message.
3. If registered → get children via `get_user_children()`.
4. If >1 child → show inline keyboard with child names (callback_data: `sched:child:{student_id}`).
5. If 1 child → proceed directly.
6. Ensure valid token via `token_manager.ensure_token()` → checks `token_expires_at`, re-auths if expired, updates DB.
7. Call `MeshClient.get_schedule(student_id, date, token)` → get `List[Lesson]`.
8. Format lessons into text message (number, time, subject, room, teacher).
9. Attach inline keyboard: `[📅 Сегодня] [📅 Завтра] [📅 Неделя]` (callback_data: `sched:period:{student_id}:{period}`).
10. On period button press → edit message with new schedule for selected period.
11. Week view: 5 sequential API calls (Mon–Fri), concatenated in one message with day headers.
12. On error → show error message + `[🔄 Повторить]` button (callback_data: `sched:retry:{student_id}:{period}`).

**Callback data format:** `sched:{action}:{student_id}:{extra}` — all state is in the button, no FSM needed.

## Decisions

### Decision 1: Callback data vs FSM for state

**Decision:** Store child_id and period in callback_data, not FSM.
**Rationale:** MemoryStorage loses state on restart. Callback data persists in Telegram messages, so buttons work even after bot restart.
**Alternatives considered:** FSM state — rejected because state is lost on restart and adds complexity.

### Decision 2: Token refresh in a separate utility

**Decision:** Create `utils/token_manager.py` with `ensure_token(user_id)` function.
**Rationale:** Token refresh logic will be needed by every future command (/ocenki, /dz). Extracting it avoids duplication.
**Alternatives considered:** Inline in handler — rejected because it would be duplicated in every command. Middleware — rejected because planned for later phase, overkill for now.

### Decision 3: Week view implementation

**Decision:** 5 sequential API calls (Mon–Fri), one per day. All days in one message.
**Rationale:** MeSH API accepts only a single date per request. Sequential calls avoid race conditions. 5 calls is within the 30/min rate limit.
**Alternatives considered:** Parallel calls with asyncio.gather — rejected because sequential is simpler and 5 calls complete fast enough (< 5 seconds total).

### Decision 4: Auth check without middleware

**Decision:** Check registration directly in handler via `get_user()`.
**Rationale:** Auth middleware is planned for a later phase. Adding it now for one handler is premature.
**Alternatives considered:** Auth middleware — rejected, deferred to later phase.

## Data Models

No new DB tables or models. Using existing:

- `users` table — `mesh_login`, `mesh_password`, `mesh_token`, `token_expires_at`
- `children` table — `student_id`, `first_name`, `last_name`, `class_name`
- `Lesson` dataclass — `number`, `subject`, `time_start`, `time_end`, `teacher`, `room`

## Dependencies

### New packages

None.

### Using existing (from project)

- `mesh_api.client.MeshClient` — `get_schedule()`, `authenticate()`
- `mesh_api.models.Lesson` — schedule data structure
- `mesh_api.exceptions` — `AuthenticationError`, `NetworkError`, `MeshAPIError`, `InvalidResponseError`
- `database.crud` — `get_user()`, `get_user_children()`, `update_user_token()`, `user_exists()`
- `config.settings` — `TIMEZONE` for date calculations

## Testing Strategy

**Feature size:** M

### Unit tests

- `test_format_schedule`: Lesson list → formatted text string (various cases: full data, missing teacher, missing room, empty list)
- `test_format_week`: Multiple days → concatenated text with day headers
- `test_callback_data_parsing`: Parse `sched:period:123:today` → correct action, student_id, period
- `test_token_needs_refresh`: Various token_expires_at values → correct boolean
- `test_get_week_dates`: Given any date → returns correct Mon–Fri dates for that week

### Integration tests

- Test MeshClient.get_schedule() with real API (requires .env with credentials)
- Test token refresh flow: expired token → re-auth → new token saved

### E2E tests

None — manual testing via Telegram with real account.

## Agent Verification Plan

**Source:** user-spec "Как проверить" section.

### Verification approach

Agent verifies import correctness and code structure. User verifies live Telegram interaction.

### Per-task verification

| Task | verify: | What to check |
|------|---------|--------------|
| 1 | bash | `python -c "from utils.token_manager import ensure_token"` — imports without error |
| 2 | bash | `python -c "from handlers.schedule import router"` — imports without error |
| 3 | bash | `grep "schedule" bot.py` — router registered |
| 4 | bash | `pytest tests/ -v` — all tests pass |

### Tools required

bash — import checks, grep, pytest.

## Risks

| Risk | Mitigation |
|------|-----------|
| MeSH API changes response format | `get_schedule()` already handles two key variants (`schedule` / `lessons`). InvalidResponseError caught and shown as user-friendly message. |
| Token auto-refresh fails (credentials changed at MeSH) | Catch AuthenticationError during refresh → show "Перерегистрируйтесь: /start" |
| Week view uses 5 API calls, eating rate limit budget | Sequential calls with existing RateLimiter. 5 calls out of 30/min is acceptable. Log warning if rate limit hit. |
| Empty schedule fields (null teacher/room) | Format function skips null fields gracefully — no crash |

## Acceptance Criteria

Technical acceptance criteria (supplement user-spec criteria):

- [ ] `handlers/schedule.py` defines `router` with command handler and callback handlers
- [ ] `utils/token_manager.py` provides `ensure_token(user_id)` returning valid token or raising AuthenticationError
- [ ] `bot.py` imports and registers `schedule.router`
- [ ] All callback_data follows format `sched:{action}:{student_id}:{extra}`
- [ ] Token refresh is logged at INFO level: "token refreshed for user {id}"
- [ ] API errors logged at ERROR level
- [ ] Unit tests pass: formatting, callback parsing, date calculations, token check
- [ ] No regressions in existing code (bot starts, /start still works)

## Implementation Tasks

<!-- Tasks are brief scope descriptions. AC, TDD, and detailed steps are created during task-decomposition. -->

### Wave 1 (независимые)

#### Task 1: Token manager utility
- **Description:** Create `utils/token_manager.py` with `ensure_token(user_id)` function. Checks token expiration, re-authenticates via MeshClient if expired, updates DB. Needed by schedule handler and all future data commands.
- **Skill:** code-writing
- **Reviewers:** code-reviewer, security-auditor, test-reviewer
- **Verify:** bash — `python -c "from utils.token_manager import ensure_token"`
- **Files to modify:** `utils/token_manager.py` (create), `utils/__init__.py`
- **Files to read:** `database/crud.py`, `mesh_api/client.py`, `mesh_api/auth.py`, `mesh_api/exceptions.py`, `config.py`

#### Task 2: Schedule handler and keyboards
- **Description:** Create `handlers/schedule.py` with `/raspisanie` command, callback handlers for child selection, period switching, and retry. Uses inline keyboards with callback_data encoding. Formats Lesson objects into readable text.
- **Skill:** code-writing
- **Reviewers:** code-reviewer, security-auditor, test-reviewer
- **Verify:** bash — `python -c "from handlers.schedule import router"`
- **Files to modify:** `handlers/schedule.py` (create)
- **Files to read:** `handlers/start.py`, `handlers/registration.py`, `database/crud.py`, `mesh_api/client.py`, `mesh_api/models.py`, `mesh_api/exceptions.py`, `utils/token_manager.py`

### Wave 2 (зависит от Wave 1)

#### Task 3: Register router and integration
- **Description:** Import schedule handler in bot.py and register its router. Verify the bot starts without errors and all existing functionality still works.
- **Skill:** code-writing
- **Reviewers:** code-reviewer
- **Verify:** bash — `grep "schedule" bot.py` and `python -c "from bot import *"`
- **Files to modify:** `bot.py`
- **Files to read:** `handlers/schedule.py`

#### Task 4: Unit tests
- **Description:** Write unit tests for schedule formatting, callback data parsing, date calculations (week dates), and token expiration check. Use mocks for MeshClient and database functions.
- **Skill:** code-writing
- **Reviewers:** code-reviewer, test-reviewer
- **Verify:** bash — `pytest tests/ -v`
- **Files to modify:** `tests/test_schedule.py` (create), `tests/__init__.py` (create), `tests/conftest.py` (create)
- **Files to read:** `handlers/schedule.py`, `utils/token_manager.py`, `mesh_api/models.py`

### Final Wave

#### Task 5: Pre-deploy QA
- **Description:** Acceptance testing: run all tests, verify acceptance criteria from user-spec and tech-spec.
- **Skill:** pre-deploy-qa
- **Reviewers:** none
