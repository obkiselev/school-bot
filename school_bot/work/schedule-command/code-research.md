# Code Research: schedule-command

Created: 2026-02-27

---

## 1. Entry Points

### Bot entry point
- **File:** `E:/claude/school_bot/bot.py`
- Main function initializes database, creates Bot and Dispatcher, registers routers via `dp.include_router()`.
- Routers are imported from handler modules and registered in order: `start.router`, `registration.router`.
- Uses `MemoryStorage` for FSM state storage.
- A new handler module (e.g., `handlers/schedule.py`) must be imported and its `router` registered here via `dp.include_router(schedule.router)`.

### Existing handler: /start
- **File:** `E:/claude/school_bot/handlers/start.py`
- Defines `router = Router()`.
- Single handler `cmd_start(message: Message, state: FSMContext)` decorated with `@router.message(Command("start"))`.
- Checks `await user_exists(user_id)` to decide between welcome-back menu or registration flow.
- Already lists `/raspisanie` in the menu text returned to registered users.

### Existing handler: registration
- **File:** `E:/claude/school_bot/handlers/registration.py`
- Defines `router = Router()`.
- Uses FSM states from `states.registration.RegistrationStates`.
- Handler pattern: state-based handlers decorated with `@router.message(SomeState)` for text input, `@router.callback_query(SomeState, F.data...)` for inline button callbacks.
- Creates `MeshClient()` inline, uses it in try/except/finally with `await client.close()`.
- Error handling pattern: catches `AuthenticationError`, `NetworkError`, `MeshAPIError` separately with user-friendly messages in Russian.
- Uses `parse_mode="HTML"` for formatted messages.
- Inline keyboard built with `InlineKeyboardMarkup` and `InlineKeyboardButton` directly (no keyboard helper module).

**Pattern for new handler:**
```python
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

router = Router()

@router.message(Command("raspisanie"))
async def cmd_schedule(message: Message, state: FSMContext):
    ...
```

---

## 2. Data Layer

### Database manager
- **File:** `E:/claude/school_bot/core/database.py`
- Class `Database` wraps `aiosqlite`. Methods: `connect()`, `close()`, `execute(query, params)`, `fetchone(query, params)`, `fetchall(query, params)`.
- Global instance `db` set in `bot.py` after `init_database()`.
- Access via `get_db()` function -- raises `RuntimeError` if not initialized.
- `init_database(db_path)` reads `database/migrations/init.sql`, splits by `;`, executes each statement.

### CRUD operations
- **File:** `E:/claude/school_bot/database/crud.py`
- Key functions for schedule feature:
  - `get_user(user_id: int) -> Optional[Dict]` -- returns user dict with decrypted `mesh_login`, `mesh_password`, `mesh_token`, `token_expires_at`.
  - `user_exists(user_id: int) -> bool` -- simple existence check.
  - `get_user_children(user_id: int) -> List[Dict]` -- returns list of children dicts with `student_id`, `first_name`, `last_name`, `class_name`. Filters by `is_active = 1`.
  - `get_child(child_id: int) -> Optional[Dict]` -- get single child by child_id.
  - `update_user_token(user_id, mesh_token, token_expires_at)` -- update stored token after re-auth.
  - `log_activity(user_id, action, details)` -- activity logging.
- All functions use `get_db()` to access the global Database instance.
- Row access is positional (tuple index), not by column name.

### Database schema
- **File:** `E:/claude/school_bot/database/migrations/init.sql`

**users table:**
| Column | Type | Notes |
|--------|------|-------|
| user_id | INTEGER PK | Telegram user ID |
| username | TEXT | Telegram username |
| first_name | TEXT | |
| last_name | TEXT | |
| registered_at | DATETIME | auto |
| mesh_login | TEXT NOT NULL | encrypted |
| mesh_password | TEXT NOT NULL | encrypted |
| mesh_token | TEXT | encrypted, nullable |
| token_expires_at | DATETIME | nullable |
| last_sync | DATETIME | |
| is_active | BOOLEAN | default 1 |

**children table:**
| Column | Type | Notes |
|--------|------|-------|
| child_id | INTEGER PK AI | internal ID |
| user_id | INTEGER FK | parent reference |
| student_id | INTEGER NOT NULL | MeSH student ID (used for API calls) |
| first_name | TEXT NOT NULL | |
| last_name | TEXT NOT NULL | |
| middle_name | TEXT | |
| class_name | TEXT | e.g. "9A" |
| school_name | TEXT | |
| is_active | BOOLEAN | default 1 |
| added_at | DATETIME | auto |

**Critical field for schedule:** `children.student_id` -- this is the MeSH API student ID needed for `get_schedule(student_id, date, token)`.

Other tables: `notification_settings`, `grades_cache`, `homework_cache`, `activity_log` -- not directly needed for schedule but relevant for future integration.

---

## 3. Similar Features

No commands beyond `/start` are implemented yet. The schedule handler will be the first data-fetching command.

However, the registration handler (`handlers/registration.py`) demonstrates the full pattern for MeSH API interaction:
1. Get user credentials from database.
2. Create `MeshClient()` instance.
3. Authenticate or use stored token.
4. Call API method (e.g., `client.get_profile(token)`).
5. Handle errors with try/except for `AuthenticationError`, `NetworkError`, `MeshAPIError`.
6. Close client in `finally`.
7. Format response with emojis and HTML parse mode.

The schedule handler should follow this same pattern but without FSM (unless child selection is needed for multi-child users).

---

## 4. Integration Points

### MeSH API client -- schedule method already exists
- **File:** `E:/claude/school_bot/mesh_api/client.py`
- `MeshClient.get_schedule(student_id: int, date_str: str, token: str) -> List[Lesson]`
- Calls `SCHEDULE_URL` with params `{"student_id": student_id, "date": date_str}`.
- Returns list of `Lesson` dataclass objects.
- Handles response keys: `data.get("schedule", []) or data.get("lessons", [])`.

### MeSH API endpoint URL
- **File:** `E:/claude/school_bot/mesh_api/endpoints.py`
- `SCHEDULE_URL = "https://dnevnik.mos.ru/mobile/api/schedule"` -- already defined.
- Comment: `# Format: /schedule?student_id={id}&date={YYYY-MM-DD}`

### Lesson model
- **File:** `E:/claude/school_bot/mesh_api/models.py`
- `@dataclass Lesson`: `number: int`, `subject: str`, `time_start: str`, `time_end: str`, `teacher: Optional[str]`, `room: Optional[str]`, `lesson_type: Optional[str]`.

### Authentication flow for commands
- Token is stored encrypted in `users.mesh_token` with `token_expires_at`.
- To use stored token: call `get_user(user_id)` -> check `token_expires_at` -> if expired, re-authenticate using decrypted `mesh_login` and `mesh_password` via `client.authenticate()` -> update token via `update_user_token()`.
- No auth middleware exists yet (listed as Phase 2 planned work in PROGRESS.md).

### Imports the schedule handler will need
```python
from database.crud import get_user, get_user_children, update_user_token, log_activity, user_exists
from mesh_api.client import MeshClient
from mesh_api.models import Lesson
from mesh_api.exceptions import AuthenticationError, NetworkError, MeshAPIError
```

### Router registration in bot.py
```python
from handlers import schedule
dp.include_router(schedule.router)
```

---

## 5. Existing Tests

No test files found in the project. No `tests/` directory, no `pytest.ini`, no `conftest.py`.

The project has no testing infrastructure set up yet. Unit tests are listed as Phase 4 planned work.

If tests are to be written for the schedule handler, the following will need to be created:
- `tests/` directory structure
- pytest configuration
- Mocks for `MeshClient`, database functions (`get_user`, `get_user_children`)
- Fixtures for `Message`, `FSMContext`, `CallbackQuery` from aiogram

---

## 6. Shared Utilities

### Encryption
- **File:** `E:/claude/school_bot/core/encryption.py`
- `encrypt(plaintext: str) -> str` and `decrypt(ciphertext: str) -> str` -- convenience wrappers around global `CredentialEncryption` instance.
- Used in `crud.py` for MeSH login/password/token.
- Schedule handler does not need to call these directly -- `get_user()` already returns decrypted values.

### Config
- **File:** `E:/claude/school_bot/config.py`
- `Settings` class with `BOT_TOKEN`, `DATABASE_PATH`, `ENCRYPTION_KEY`, `MESH_BASE_URL`, `MESH_TIMEOUT`, `MESH_MAX_RETRIES`, `TIMEZONE` (default "Europe/Moscow").
- Global `settings = Settings()` instance.
- `TIMEZONE` may be useful for schedule date calculations.

### Keyboards
- **File:** `E:/claude/school_bot/keyboards/__init__.py`
- Empty file. No keyboard helpers exist.
- Registration handler builds `InlineKeyboardMarkup` inline. Schedule handler should follow the same pattern or create reusable keyboard functions in `keyboards/schedule.py`.

### States
- **File:** `E:/claude/school_bot/states/registration.py`
- `RegistrationStates(StatesGroup)` with 5 states.
- Pattern: `from aiogram.fsm.state import State, StatesGroup`.
- Schedule may need its own states if child selection or date navigation requires FSM. Example: `states/schedule.py` with `ScheduleStates(StatesGroup)`.

---

## 7. Potential Problems

### Token expiration handling (CRITICAL)
- `mesh_token` and `token_expires_at` are stored in the database but there is no helper function or middleware to check expiration and re-authenticate automatically.
- The schedule handler must implement this logic inline: check if token is expired, re-auth if needed, update stored token.
- If `mesh_token` is None (user registered but token expired/cleared), need full re-auth.
- `token_expires_at` is stored as an ISO string, not a datetime object -- parsing needed.

### No auth middleware
- No middleware to check if user is registered before command execution.
- Each handler must check `user_exists()` or `get_user()` at the start and respond with "please register first" message.
- PROGRESS.md lists auth middleware as Phase 2 planned work.

### Multi-child users
- A parent can have multiple children. The schedule handler must handle this:
  - If 1 child: show schedule directly.
  - If multiple children: ask which child's schedule to show (inline keyboard).
- This means FSM state may be needed for child selection flow.

### MeSH API instability
- The API is unofficial and may change response formats.
- `client.get_schedule()` tries both `data.get("schedule", [])` and `data.get("lessons", [])` as fallback keys.
- Error messages should tell the user to try again later.

### Rate limiting
- Global `RateLimiter` in `MeshClient` allows 30 calls per 60 seconds.
- Each schedule request uses 1 API call. If showing a full week (5-6 days), that is 5-6 calls per user action.
- For a week view, consider whether the API supports date ranges or only single dates.

### No aiohttp session reuse across commands
- `MeshClient` creates a new `aiohttp.ClientSession` each time it is instantiated.
- Each command handler creates and closes its own `MeshClient`.
- This is functional but not optimal. Not a blocker.

### Row-based database access
- `crud.py` accesses query results by tuple index (e.g., `row[0]`, `row[2]`) rather than column names.
- This is fragile -- any schema change that reorders columns will break access.
- Not a blocker for the schedule feature since we only read via existing `get_user()` and `get_user_children()` functions.

---

## 8. Constraints & Infrastructure

### Framework versions
- Python 3.9+
- aiogram 3.25 (async Telegram bot framework)
- aiosqlite (async SQLite)
- pydantic-settings (config from .env)
- cryptography (Fernet encryption)

### FSM storage
- `MemoryStorage()` is used -- FSM state is lost on bot restart.
- Not a problem for schedule command (short-lived interaction), but worth noting.

### No CI/CD, no pre-commit hooks
- No `.github/workflows/`, no `.pre-commit-config.yaml` found.
- No automated testing pipeline.

### Environment variables required
- `BOT_TOKEN` -- Telegram bot API token
- `ENCRYPTION_KEY` -- Fernet key for credential encryption
- Optional: `DATABASE_PATH`, `MESH_BASE_URL`, `LOG_LEVEL`, etc.

### Project phase
- Phase 1 completed (foundation). Phase 2 (main commands) is next.
- `/raspisanie` is the first item in Phase 2.
- Current version: 0.1.0.

---

## 9. External Libraries

### aiogram 3.x
- Handler registration: `Router()` + `@router.message(Command("..."))` decorator.
- FSM: `StatesGroup`, `State`, `FSMContext` for multi-step flows.
- Inline keyboards: `InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(...)]])`.
- Callback queries: `@router.callback_query(State, F.data == "...")`.
- Message formatting: `parse_mode="HTML"` with `<b>`, `<i>`, `<code>` tags.

### aiohttp
- Used internally by `MeshClient` for HTTP requests to MeSH API.
- `aiohttp.ClientSession`, `aiohttp.ClientTimeout`.
- Schedule handler does not interact with aiohttp directly -- uses `MeshClient` methods.

---

## Summary: What the schedule handler needs to do

1. **New file:** `E:/claude/school_bot/handlers/schedule.py` -- main handler.
2. **Registration in bot.py:** Import and register `schedule.router`.
3. **Auth check:** Call `get_user(user_id)` to verify registration and get token.
4. **Token refresh:** Check `token_expires_at`, re-auth if expired via `client.authenticate()`, save new token via `update_user_token()`.
5. **Child selection:** Call `get_user_children(user_id)`. If one child, proceed. If multiple, show inline keyboard for selection.
6. **API call:** `client.get_schedule(student_id, date_str, token)` returns `List[Lesson]`.
7. **Formatting:** Build text message from Lesson objects (number, subject, time, room, teacher).
8. **Date navigation:** Inline buttons for "Today" / "Tomorrow" / "Week" (callback queries).
9. **Error handling:** Catch `AuthenticationError`, `NetworkError`, `MeshAPIError`.
10. **Optional FSM states:** `states/schedule.py` if child-selection or date-navigation requires state tracking.
11. **Optional keyboards:** `keyboards/schedule.py` for reusable keyboard builders.

### Files to create
| File | Purpose |
|------|---------|
| `handlers/schedule.py` | Command handler and callback handlers |
| `states/schedule.py` | FSM states (if needed for multi-child selection) |
| `keyboards/schedule.py` | Keyboard builders (optional, could be inline) |

### Files to modify
| File | Change |
|------|--------|
| `bot.py` | Import and register `schedule.router` |

### Files to read (no changes)
| File | Why |
|------|-----|
| `database/crud.py` | Use `get_user()`, `get_user_children()`, `update_user_token()`, `log_activity()` |
| `mesh_api/client.py` | Use `MeshClient.get_schedule()`, `MeshClient.authenticate()` |
| `mesh_api/models.py` | Lesson dataclass fields for formatting |
| `mesh_api/exceptions.py` | Exception classes for error handling |
| `config.py` | `settings.TIMEZONE` for date handling |
