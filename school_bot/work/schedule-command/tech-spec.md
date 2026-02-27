---
created: 2026-02-27
status: approved
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
2. If not registered → reply "Сначала зарегистрируйтесь: /start".
3. If registered → get children via `get_user_children()`.
4. If >1 child → show inline keyboard with child names (callback_data: `sched:child:{student_id}`).
5. If 1 child → proceed directly.
6. **Ownership check:** every callback handler verifies that `student_id` from callback_data belongs to `callback.from_user.id` via `get_user_children()`. If not — silently ignore (log at WARNING).
7. Ensure valid token via `token_manager.ensure_token()` → checks `token_expires_at`, re-auths if expired, updates DB. If re-auth fails → reply "Не удалось подключиться к МЭШ. Перерегистрируйтесь: /start".
8. Call `MeshClient.get_schedule(student_id, date, token)` → get `List[Lesson]`.
9. If empty list → reply "На этот день уроков нет" with period buttons still visible.
10. If non-empty → format lessons into text message (number, time, subject, room, teacher). Skip null fields gracefully.
11. Attach inline keyboard: `[📅 Сегодня] [📅 Завтра] [📅 Неделя]` (callback_data: `sched:period:{student_id}:{period}`).
12. On period button press → edit message with new schedule for selected period.
13. Week view: 5 sequential API calls (Mon–Fri), concatenated in one message with day headers. If a single day fails → skip that day with a note "Не удалось загрузить" and continue. If all 5 fail → show error message.
14. On error → show "Сервис МЭШ временно недоступен, попробуйте позже" + `[🔄 Повторить]` button (callback_data: `sched:retry:{student_id}:{period}`).
15. **Malformed callback_data:** if parsing fails (wrong format, non-integer student_id) → answer callback with no action, log at WARNING. No crash.

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

### Decision 5: Ownership verification on every callback

**Decision:** Every callback handler verifies that `student_id` belongs to the calling user before making API calls.
**Rationale:** Telegram callback_data is visible and forgeable. Without verification, any user could craft a callback with another child's student_id (IDOR vulnerability).
**Alternatives considered:** Trust callback_data — rejected due to security risk.

### Decision 6: Token expiry with safety buffer

**Decision:** `ensure_token()` considers token expired if `token_expires_at` is within 5 minutes of now (safety buffer). Current `auth.py` hardcodes 24h expiry — use that as-is but add the buffer.
**Rationale:** If the real token expires slightly before our stored `token_expires_at`, the API call fails. A 5-minute buffer prevents this edge case.
**Alternatives considered:** Parse expiry from API response — would require changing `auth.py`, out of scope for this feature.

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
- `mesh_api.client.RateLimiter` — rate limiting built into MeshClient, applied automatically to all API calls

## Testing Strategy

**Feature size:** M

### Unit tests

- `test_format_schedule`: Lesson list → formatted text string (full data, missing teacher, missing room, empty list → "На этот день уроков нет")
- `test_format_week`: Multiple days → concatenated text with day headers; some days empty → only non-empty shown
- `test_callback_data_parsing`: Parse `sched:period:123:today` → correct action, student_id, period; malformed input → None/error without crash
- `test_token_needs_refresh`: Various token_expires_at values → correct boolean (including 5-min buffer)
- `test_get_week_dates`: Given any date → returns correct Mon–Fri dates for that week
- `test_unregistered_user`: Handler returns "Сначала зарегистрируйтесь: /start" when `get_user()` returns None
- `test_api_error_message`: Handler returns "Сервис МЭШ временно недоступен" + retry button on NetworkError/MeshAPIError
- `test_token_refresh_failure`: Handler returns "Перерегистрируйтесь: /start" when ensure_token raises AuthenticationError
- `test_child_selection_keyboard`: Multiple children → inline keyboard with child names; single child → no selection step
- `test_ownership_check`: Callback with student_id not belonging to user → silently ignored

### Integration tests

- Test token refresh flow with mocked HTTP: expired token → re-auth call → new token saved to DB; assertions on `update_user_token()` call args
- Test token refresh failure with mocked HTTP: re-auth returns 401 → AuthenticationError raised

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
| 5 | bash | `pytest tests/ -v` — all tests pass, acceptance criteria verified |

### Tools required

bash — import checks, grep, pytest.

## Risks

| Risk | Mitigation |
|------|-----------|
| MeSH API changes response format | `get_schedule()` already handles two key variants (`schedule` / `lessons`). InvalidResponseError caught and shown as user-friendly message. |
| Token auto-refresh fails (credentials changed at MeSH) | Catch AuthenticationError during refresh → show "Перерегистрируйтесь: /start" |
| Week view uses 5 API calls, eating rate limit budget | Sequential calls with existing RateLimiter. 5 calls out of 30/min is acceptable. Log warning if rate limit hit. |
| Empty schedule fields (null teacher/room) | Format function skips null fields gracefully — no crash |
| IDOR via forged callback_data | Every callback handler verifies student_id ownership before API call. Unowned student_id → silently ignored, logged at WARNING |
| Malformed callback_data | Parse with try/except, answer callback with no action on failure, log at WARNING |
| Decrypted credentials in memory | `ensure_token()` receives only user_id, fetches credentials internally, does not pass them through function chain. Logging excludes credential fields |

## Acceptance Criteria

Technical acceptance criteria (supplement user-spec criteria):

- [ ] `handlers/schedule.py` defines `router` with command handler and callback handlers
- [ ] `utils/token_manager.py` provides `ensure_token(user_id)` returning valid token or raising AuthenticationError
- [ ] `bot.py` imports and registers `schedule.router`
- [ ] All callback_data follows format `sched:{action}:{student_id}:{extra}`
- [ ] Every callback handler verifies student_id ownership before API call (IDOR protection)
- [ ] Malformed callback_data handled gracefully (no crash, logged at WARNING)
- [ ] Token refresh is logged at INFO level: "token refreshed for user {id}"
- [ ] Token expiry check uses 5-minute safety buffer
- [ ] API errors logged at ERROR level
- [ ] Ownership violations logged at WARNING level
- [ ] Credentials never appear in log output
- [ ] Unit tests pass: formatting, callback parsing, date calculations, token check, error paths, ownership
- [ ] No regressions in existing code (bot starts, /start still works)

## Implementation Tasks

<!-- Tasks are brief scope descriptions. AC, TDD, and detailed steps are created during task-decomposition. -->

### Wave 1

#### Task 1: Token manager utility
- **Description:** Create `utils/token_manager.py` with `ensure_token(user_id)` function. Checks token expiration (with 5-min buffer), re-authenticates via MeshClient if expired, updates DB. Needed by schedule handler and all future data commands.
- **Skill:** code-writing
- **Reviewers:** code-reviewer, security-auditor, test-reviewer
- **Verify:** bash — `python -c "from utils.token_manager import ensure_token"`
- **Files to modify:** `utils/token_manager.py` (create), `utils/__init__.py`
- **Files to read:** `database/crud.py`, `mesh_api/client.py`, `mesh_api/auth.py`, `mesh_api/exceptions.py`, `config.py`

### Wave 2 (зависит от Wave 1)

#### Task 2: Schedule handler and keyboards
- **Description:** Create `handlers/schedule.py` with `/raspisanie` command, callback handlers for child selection, period switching, and retry. Includes IDOR protection (ownership check on every callback) and graceful handling of malformed callback_data.
- **Skill:** code-writing
- **Reviewers:** code-reviewer, security-auditor, test-reviewer
- **Verify:** bash — `python -c "from handlers.schedule import router"`
- **Files to modify:** `handlers/schedule.py` (create)
- **Files to read:** `handlers/start.py`, `handlers/registration.py`, `database/crud.py`, `mesh_api/client.py`, `mesh_api/models.py`, `mesh_api/exceptions.py`, `utils/token_manager.py`

#### Task 3: Register router and integration
- **Description:** Import schedule handler in bot.py and register its router. Verify the bot starts without errors and all existing functionality still works.
- **Skill:** code-writing
- **Reviewers:** code-reviewer
- **Verify:** bash — `grep "schedule" bot.py`
- **Files to modify:** `bot.py`
- **Files to read:** `handlers/schedule.py`

### Wave 3 (зависит от Wave 2)

#### Task 4: Unit tests
- **Description:** Write unit tests for schedule formatting, callback data parsing, date calculations, token expiration check, error paths (unregistered user, API error, token refresh failure), ownership check, and child selection keyboard.
- **Skill:** code-writing
- **Reviewers:** code-reviewer, security-auditor, test-reviewer
- **Verify:** bash — `pytest tests/ -v`
- **Files to modify:** `tests/test_schedule.py` (create), `tests/__init__.py` (create), `tests/conftest.py` (create)
- **Files to read:** `handlers/schedule.py`, `utils/token_manager.py`, `mesh_api/models.py`

### Final Wave

#### Task 5: Pre-deploy QA
- **Description:** Acceptance testing: run all tests, verify acceptance criteria from user-spec and tech-spec.
- **Skill:** pre-deploy-qa
- **Reviewers:** none
- **Verify:** bash — `pytest tests/ -v`
- **Files to read:** `work/schedule-command/user-spec.md`, `work/schedule-command/tech-spec.md`
