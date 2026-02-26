# Code Research: Access Control

## 1. Entry Points

### 1.1 Application Bootstrap — `E:\claude\school_helper\run.py`

The main entry point. Creates `Bot` and `Dispatcher`, registers all routers, starts polling.

```python
async def main():
    from bot.db.database import get_db, close_db
    await get_db()

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    # Routers registered in this order:
    dp.include_router(start.router)      # /start, go_home callback
    dp.include_router(language.router)    # start_test, lang:* callbacks
    dp.include_router(topic.router)       # topic:*, back_to_topic, custom topic text
    dp.include_router(settings.router)    # count:* callback (question count)
    dp.include_router(quiz.router)        # ans:*, cancel_quiz, text answers
    dp.include_router(results.router)     # (no direct handlers — called from quiz)
    dp.include_router(history.router)     # my_results callback

    await dp.start_polling(bot)
```

Key facts for middleware integration:
- `dp` is the `Dispatcher` instance — middleware attaches here via `dp.message.middleware()` and `dp.callback_query.middleware()`.
- No middleware is currently registered.
- The `Dispatcher` uses `MemoryStorage()` for FSM.
- Database is initialized before dispatcher starts, so DB queries are available during middleware execution.

### 1.2 Start Handler — `E:\claude\school_helper\bot\handlers\start.py`

Two handlers:

```python
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await ensure_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    await message.answer(WELCOME_TEXT, reply_markup=main_menu_keyboard())

@router.callback_query(F.data == "go_home")
async def go_home(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(WELCOME_TEXT, reply_markup=main_menu_keyboard())
```

`ensure_user()` is called on every `/start` — this is where user records are created/updated. The access check middleware must run before this handler. If a blocked user sends `/start`, they should get "Access restricted" and `ensure_user` should NOT be called.

### 1.3 All Handlers Summary

| File | Trigger | Type | Handler |
|------|---------|------|---------|
| `bot/handlers/start.py` | `/start` command | Message | `cmd_start` |
| `bot/handlers/start.py` | `go_home` callback | CallbackQuery | `go_home` |
| `bot/handlers/language.py` | `start_test` callback | CallbackQuery | `choose_language` |
| `bot/handlers/language.py` | `lang:*` callback (in FSM state) | CallbackQuery | `language_selected` |
| `bot/handlers/topic.py` | `topic:*` callback (in FSM state) | CallbackQuery | `topic_selected` |
| `bot/handlers/topic.py` | `back_to_topic` callback | CallbackQuery | `back_to_topic` |
| `bot/handlers/topic.py` | text message (in FSM state) | Message | `custom_topic_entered` |
| `bot/handlers/settings.py` | `count:*` callback (in FSM state) | CallbackQuery | `count_selected` |
| `bot/handlers/quiz.py` | `ans:*` callback (in FSM state) | CallbackQuery | `answer_via_button` |
| `bot/handlers/quiz.py` | text message (in FSM state) | Message | `answer_via_text` |
| `bot/handlers/quiz.py` | `cancel_quiz` callback | CallbackQuery | `cancel_quiz` |
| `bot/handlers/history.py` | `my_results` callback | CallbackQuery | `show_history` |

All handlers receive either `Message` or `CallbackQuery`. Both update types need access checking.

---

## 2. Data Layer

### 2.1 Database Connection — `E:\claude\school_helper\bot\db\database.py`

Singleton `aiosqlite` connection stored in module-level `_db` variable.

```python
_db: aiosqlite.Connection | None = None

async def get_db() -> aiosqlite.Connection:
async def close_db():
async def _create_tables(db: aiosqlite.Connection):
```

Tables are auto-created on first `get_db()` call via `_create_tables()`. This uses `CREATE TABLE IF NOT EXISTS`, so adding new columns requires `ALTER TABLE` or a new table.

### 2.2 Current `users` Table Schema

```sql
CREATE TABLE IF NOT EXISTS users (
    user_id       INTEGER PRIMARY KEY,   -- Telegram user ID
    username      TEXT,                   -- @username (nullable)
    first_name    TEXT,                   -- Display name (nullable)
    created_at    TEXT DEFAULT (datetime('now')),
    last_active   TEXT DEFAULT (datetime('now'))
);
```

Current data: 2 users exist (user_id 805271990 `@obkiselev` and 6766561421).

**No `role` or `status` columns exist.** Options for extending:
- **Option A: ALTER TABLE** — add `role TEXT DEFAULT 'student'` and `status TEXT DEFAULT 'pending'` columns. Works with `CREATE TABLE IF NOT EXISTS` pattern by running `ALTER TABLE` separately with error handling for "column already exists".
- **Option B: New table** — `allowed_users(user_id INTEGER PRIMARY KEY, role TEXT, status TEXT, added_by INTEGER, added_at TEXT)`. Cleaner separation but requires JOIN or separate lookup.

Option A is simpler and matches the existing pattern where `ensure_user` already does upsert on the `users` table.

### 2.3 Queries Module — `E:\claude\school_helper\bot\db\queries.py`

Current functions:

```python
async def ensure_user(user_id: int, username: str | None, first_name: str | None):
async def save_test_session(user_id, language, topic, total, correct, percent, answers) -> int:
async def get_user_sessions(user_id: int, limit: int = 10) -> list[dict]:
async def get_weak_topics(user_id: int) -> list[dict]:
async def get_recent_questions(user_id, language, topic, limit=50) -> list[str]:
async def get_stats_summary(user_id: int) -> dict:
```

`ensure_user()` does INSERT ... ON CONFLICT UPDATE. For access control, new queries needed:
- `get_user_role(user_id) -> str | None` — check if user is allowed and what role
- `set_user_role(user_id, role)` — admin command to allow/block
- `get_all_users()` — for `/users` admin command
- `is_user_allowed(user_id) -> bool` — fast check for middleware

### 2.4 Models — `E:\claude\school_helper\bot\db\models.py`

Only TypedDicts for type hints, no ORM:

```python
class AnswerRecord(TypedDict): ...
class SessionSummary(TypedDict): ...
```

No user model exists. A new `UserRecord` TypedDict could be added for consistency.

### 2.5 Other Tables

```sql
test_sessions (id, user_id, language, topic, total_questions, correct_answers, score_percent, started_at, finished_at)
question_results (id, session_id, question_type, question_text, correct_answer, user_answer, is_correct, explanation)
```

These tables use `user_id` as a foreign key. Blocking a user should NOT delete their test history data.

---

## 3. Similar Features

There are no existing features in this codebase that implement user filtering, role-based access, or middleware. This is the first access-control implementation.

However, the `ensure_user()` pattern in `bot/db/queries.py` provides a relevant model: it runs on every `/start` to upsert user data. An access-check function would follow a similar pattern — query the database for a user_id and return a result.

---

## 4. Integration Points

### 4.1 Dispatcher Middleware Hook — `E:\claude\school_helper\run.py`

aiogram 3.x supports outer and inner middleware on the Dispatcher, Router, and per-update-type level. The most complete approach for access control is to register middleware on the Dispatcher level for both `message` and `callback_query` event types:

```python
# In run.py, after creating dp, before include_router:
dp.message.outer_middleware(AccessControlMiddleware())
dp.callback_query.outer_middleware(AccessControlMiddleware())
```

Outer middleware runs before any router/handler filtering. This means even if a handler has an FSM state filter, the middleware runs first and can block the update.

aiogram middleware signature:

```python
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

class AccessControlMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        # Check access here
        # If allowed: return await handler(event, data)
        # If blocked: send "access restricted" and return (don't call handler)
```

### 4.2 Config / Environment — `E:\claude\school_helper\bot\config.py`

Currently loads from `.env`:

```python
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://localhost:1234/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen2.5-7b-instruct")
DB_PATH = os.getenv("DB_PATH", "data/school_helper.db")
```

For access control, a new config value is needed:
```python
ADMIN_IDS = [int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]
```

This defines who is an admin (by Telegram user ID). At least one admin must be configured in `.env` for the system to work. The current primary user is `805271990` (`@obkiselev`).

`.env.example` would need updating to include `ADMIN_IDS=`.

### 4.3 Main Menu Keyboard — `E:\claude\school_helper\bot\keyboards\main_menu.py`

```python
def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="... Пройти тест", callback_data="start_test")],
        [InlineKeyboardButton(text="... Мои результаты", callback_data="my_results")],
        [InlineKeyboardButton(text="... Начать заново", callback_data="go_home")],
    ])
```

For admin users, an "Admin panel" button could be conditionally added. However, the keyboard is currently built without user context (no user_id parameter). This would need to change to `main_menu_keyboard(is_admin: bool = False)` or the admin commands could be purely text-based (`/allow`, `/block`, `/users`).

### 4.4 Database Initialization Order

In `run.py`, `await get_db()` is called before the dispatcher starts polling. This means the database (and any new tables/columns) will be ready before any middleware or handler runs. The access-check middleware can safely call DB queries.

---

## 5. Existing Tests

There are no test files in the project. No `tests/` directory, no `pytest.ini`, no `conftest.py`.

```
$ find . -name "test_*" -o -name "*_test.py" -o -name "conftest.py"
(no results)
```

The project uses no testing framework currently. `requirements.txt` does not include pytest or any test runner.

For the access-control feature, tests would be the first tests in this project. Recommended setup:
- Add `pytest` and `pytest-asyncio` to requirements.
- Create `tests/` directory with `conftest.py`.
- Test the middleware logic, DB queries, and admin command handlers in isolation.

---

## 6. Shared Utilities

### 6.1 `bot/utils/__init__.py`

Empty file. The `bot/utils/` directory exists but has no code. This is a good location for the access-control middleware module.

### 6.2 `bot/db/database.py` — `get_db()`

The shared database connection getter. All queries use `db = await get_db()` to obtain the connection. The middleware will use the same pattern.

### 6.3 `bot/db/queries.py` — `ensure_user()`

The upsert function for user records. This is the closest existing pattern to what the access-control queries will look like. It demonstrates the project's query style: raw SQL with `aiosqlite`, no ORM.

### 6.4 `bot/config.py`

Central configuration. All environment variables are loaded here. New config values (like `ADMIN_IDS`) should go here.

---

## 7. Potential Problems

### 7.1 FSM State Orphaning on Block

If a user is blocked while mid-test (FSM state is `QuizFlow.answering_question`), their FSM state remains in `MemoryStorage`. This is not a data leak risk (MemoryStorage is ephemeral), but:
- If the user is later unblocked, their stale FSM state may cause unexpected behavior.
- The middleware should call `state.clear()` when blocking a user who has active FSM state, OR the `/start` handler already clears state (`await state.clear()`), so unblocking + /start would reset naturally.
- Since `MemoryStorage` is used, state is lost on bot restart anyway. Low risk.

### 7.2 Database Migration for Existing Users

The `users` table already has 2 rows. Adding `role` and `status` columns via `ALTER TABLE` must handle:
- Default values for existing users (both should become `student` + `allowed`, or `student` + `pending` depending on policy).
- The admin user (805271990) needs to be set as `admin` + `allowed` either via migration or via `ADMIN_IDS` config.

Recommended approach: `ADMIN_IDS` in `.env` is the source of truth for admin status. The DB `role` column is for students only. If `user_id` is in `ADMIN_IDS`, they are admin regardless of DB value.

### 7.3 Race Condition: Concurrent Updates

`aiosqlite` uses a single connection (`_db` singleton). SQLite handles concurrent writes with a write lock. Since the bot is single-process and `aiosqlite` serializes operations, there is no practical race condition risk for user role updates.

### 7.4 Callback Query Error Handling

When middleware blocks a `CallbackQuery`, it should call `await callback.answer()` to dismiss the loading spinner in Telegram. If the middleware only blocks without answering, the user sees an infinite loading indicator on the button.

### 7.5 No Input Validation on Admin Commands

The `/allow` and `/block` commands will accept user IDs or usernames. Validation needed:
- Is the target a valid Telegram user ID?
- Can an admin block themselves? (should be prevented)
- Can an admin block another admin? (should be prevented if only one admin, or require super-admin)

### 7.6 ensure_user() Called Before Access Check

Currently `cmd_start` calls `ensure_user()` which creates a DB record for any user who sends `/start`. If middleware blocks the user before the handler runs, `ensure_user()` will NOT be called, so unknown users will NOT have a DB record. The admin needs a way to allow users by Telegram user_id even if they have no DB record yet. The `/allow <user_id>` command should create the record.

---

## 8. Constraints & Infrastructure

### 8.1 Framework

- **aiogram 3.25.0+** — modern async Telegram bot framework. Supports middleware via `BaseMiddleware`. Routers are composable.
- **Python 3.11+** — inferred from `type | None` syntax in the codebase and `__pycache__` files showing cpython-311.
- **aiosqlite 0.20.0+** — async SQLite wrapper.
- **openai 1.50.0+** — used for LLM Studio client (OpenAI-compatible API).

### 8.2 Dependencies (`E:\claude\school_helper\requirements.txt`)

```
aiogram>=3.25.0
openai>=1.50.0
aiosqlite>=0.20.0
python-dotenv>=1.0.0
```

No new dependencies needed for access control. aiogram's `BaseMiddleware` is built-in.

### 8.3 Environment Variables (`E:\claude\school_helper\.env`)

```
BOT_TOKEN=<token>
LLM_BASE_URL=http://localhost:1234/v1
LLM_MODEL=qwen2.5-vl-7b
DB_PATH=data/school_helper.db
```

New variable needed: `ADMIN_IDS` (comma-separated list of Telegram user IDs).

### 8.4 Deployment

No CI/CD, no Dockerfile, no deployment scripts visible. The bot runs directly via `python run.py`. Deployment changes for access control are limited to:
- Update `.env` with `ADMIN_IDS`.
- Restart the bot (DB migration happens automatically on startup).

### 8.5 Git / Versioning

Current version: `0.1.2`. Version is tracked in `package.json` and `PROGRESS.md`. Next version for this feature would be `0.1.3`.

---

## 9. External Libraries

### 9.1 aiogram Middleware API (aiogram 3.x)

aiogram provides `BaseMiddleware` for creating middleware classes. Key API:

```python
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from typing import Callable, Awaitable, Any

class MyMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        # pre-processing
        result = await handler(event, data)  # call next middleware or handler
        # post-processing
        return result
```

Registration on Dispatcher:
```python
dp.message.middleware(MyMiddleware())           # inner middleware
dp.message.outer_middleware(MyMiddleware())     # outer middleware (runs first)
dp.callback_query.middleware(MyMiddleware())
dp.callback_query.outer_middleware(MyMiddleware())
```

**Outer vs Inner middleware:** Outer middleware runs before the router's filters evaluate. Inner middleware runs after the router finds a matching handler but before the handler executes. For access control, **outer middleware** is correct — we want to block access before any filter or handler runs.

### 9.2 aiogram Filters

aiogram has a `CommandStart()` filter used in `start.py`. For admin commands, `Command("allow")`, `Command("block")`, `Command("users")` filters can be used:

```python
from aiogram.filters import Command
@router.message(Command("allow"))
async def cmd_allow(message: Message): ...
```

### 9.3 aiogram `message.from_user`

Both `Message.from_user` and `CallbackQuery.from_user` provide the Telegram `User` object with `.id`, `.username`, `.first_name`. Available in middleware via `event.from_user`.

### 9.4 aiosqlite

Already used throughout the project. No new patterns needed. The existing `get_db()` singleton pattern works for middleware queries.

---

## Summary of Files to Modify

| File | Change |
|------|--------|
| `E:\claude\school_helper\bot\config.py` | Add `ADMIN_IDS` config |
| `E:\claude\school_helper\.env` | Add `ADMIN_IDS=805271990` |
| `E:\claude\school_helper\.env.example` | Add `ADMIN_IDS=` |
| `E:\claude\school_helper\bot\db\database.py` | Add `role` and `status` columns to `users` table (ALTER TABLE migration) |
| `E:\claude\school_helper\bot\db\queries.py` | Add access-control query functions |
| `E:\claude\school_helper\bot\db\models.py` | Optionally add `UserRecord` TypedDict |
| `E:\claude\school_helper\run.py` | Register middleware on dispatcher |
| **New file:** `E:\claude\school_helper\bot\middleware\__init__.py` | Empty init |
| **New file:** `E:\claude\school_helper\bot\middleware\access.py` | `AccessControlMiddleware` class |
| **New file:** `E:\claude\school_helper\bot\handlers\admin.py` | Admin command handlers (`/allow`, `/block`, `/users`) |
| **New file:** `E:\claude\school_helper\bot\keyboards\admin_kb.py` | Optional admin keyboards |

## Summary of Files to Read (Context for Implementation)

| File | Reason |
|------|--------|
| `E:\claude\school_helper\run.py` | Understand dispatcher setup for middleware registration |
| `E:\claude\school_helper\bot\handlers\start.py` | Entry point for users, `ensure_user` call pattern |
| `E:\claude\school_helper\bot\db\database.py` | `_create_tables` function for migration logic |
| `E:\claude\school_helper\bot\db\queries.py` | Query patterns and `ensure_user` signature |
| `E:\claude\school_helper\bot\config.py` | Config loading pattern for `ADMIN_IDS` |
| `E:\claude\school_helper\bot\keyboards\main_menu.py` | If admin button is added to menu |
