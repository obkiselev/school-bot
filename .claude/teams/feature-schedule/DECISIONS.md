# Decisions Log -- /raspisanie command (schedule-command feature)

## Feature Definition of Done

- `python -c "from utils.token_manager import ensure_token"` -- без ошибок
- `python -c "from handlers.schedule import router"` -- без ошибок
- `grep "schedule" bot.py` -- роутер зарегистрирован
- `pytest tests/ -v` -- все тесты проходят
- IDOR-защита на каждом callback (проверка владения student_id)
- Credentials никогда не попадают в логи
- Обновление токена с 5-минутным буфером безопасности
- Все критерии приемки из user-spec и tech-spec выполнены

## Risks & Mitigations

### RISK-1 (CRITICAL): token_expires_at -- ISO-строка, не datetime
- **Описание:** auth.py сохраняет token_expires_at как `datetime.now().isoformat()`. crud.py возвращает row[8] как строку. token_manager должен парсить ISO-формат и сравнивать с datetime.now() + 5 мин буфер. Если парсинг сломается -- токен никогда не обновится или обновляется на каждый запрос.
- **Затронуты:** Task 1, Task 4
- **Митигация:** Явно использовать `datetime.fromisoformat()`. Обработать None (токен не получен). Тесты: None, прошлое, будущее, зона буфера.

### RISK-2 (CRITICAL): IDOR -- student_id в callback_data может быть подделан
- **Описание:** Callback_data содержит student_id. Без ownership-проверки на каждом callback -- видно расписание чужих детей.
- **Затронуты:** Task 2
- **Митигация:** Каждый callback-хендлер вызывает get_user_children() и проверяет принадлежность student_id. Нет -- callback.answer() без действий, лог WARNING.

### RISK-3 (MAJOR): MeshClient не закрывается при ошибке в ensure_token
- **Описание:** token_manager создаст MeshClient для re-auth. Без finally-закрытия -- утечка aiohttp-сессий.
- **Затронуты:** Task 1
- **Митигация:** ensure_token использует try/finally для закрытия MeshClient.

### RISK-4 (MAJOR): Неделя -- частичные ошибки при 5 API-запросах
- **Описание:** Один из 5 запросов упал -- нужно показать остальные дни + пометку на упавшем. Все 5 упали -- общая ошибка.
- **Затронуты:** Task 2, Task 4
- **Митигация:** AC для Task 2: частичная ошибка показывает успешные дни + пометку. Тесты: все OK, один упал, все упали.

### RISK-5 (MAJOR): Telegram callback_data -- лимит 64 байта
- **Описание:** `sched:retry:123456789:week` = 29 ASCII-символов -- укладывается. Но нужна проверка при ревью.
- **Затронуты:** Task 2
- **Митигация:** Проверить максимальную длину при code review.

### RISK-6 (MINOR): Тестовая инфраструктура с нуля
- **Описание:** В проекте нет tests/, conftest.py. Task 4 создает все с нуля. Fixtures для aiogram должны корректно мокать Message, CallbackQuery.
- **Затронуты:** Task 4
- **Митигация:** Проверить fixtures при ревью Task 4.

## Architectural Decisions

## Decision: Plan validation -- 2026-02-28
Date: 2026-02-28
Context: Combined VALIDATE PLAN + IDENTIFY RISKS. Plan has 5 tasks across 3 waves. Structure is sound but task files (1.md, 2.md, 4.md) not populated -- only templates. Task 5 (.conventions/) is new, not in tech-spec. Plan validated with issues noted below.
Alternatives considered: N/A -- this is a validation decision.

## Decision: Task file templates not filled -- tasks 1, 2, 4 are blank templates
Date: 2026-02-28
Context: During initial plan review, discovered that task files 1.md, 2.md, and 4.md contain only the blank template with placeholder content ("Task N: Название", "Критерий 1", etc). Only task 3.md has a real description. The tech-spec has the real task descriptions in its "Implementation Tasks" section, but the individual task files were not populated with specific content.
Alternatives considered: Proceed with template tasks and rely on tech-spec only -- rejected because coders need specific acceptance criteria and steps in each task file.

## Decision: Callback data format convention -- `sched:{action}:{student_id}:{extra}`
Date: 2026-02-28
Context: Tech-spec defines callback_data format for all schedule-related buttons. This establishes a prefix-based namespace convention for callback routing.
Alternatives considered: Using numeric IDs only, using JSON in callback_data -- both rejected for readability and Telegram's 64-byte callback_data limit.

## Decision: Token manager as standalone utility in utils/
Date: 2026-02-28
Context: Token refresh logic extracted to `utils/token_manager.py` for reuse across future commands (/ocenki, /dz). Not middleware because auth middleware is deferred to a later phase.
Alternatives considered: Inline in handler (duplication), middleware (premature), method on MeshClient (couples DB to API client).

## Decision: Task 1 architectural review -- APPROVED
Date: 2026-02-28
Context: Review of utils/token_manager.py. File follows project patterns (MeshClient lifecycle from registration.py, CRUD usage, exception hierarchy). RISK-1 (ISO parsing) and RISK-3 (session leak) mitigated. Pending fixes from other reviewers: asyncio.Lock per user_id (race condition), consolidate three except blocks into one except MeshAPIError.
Alternatives considered: N/A -- review decision.

## Decision: Out-of-scope issues noted for future work
Date: 2026-02-28
Context: During Task 1 review cycle, reviewers found: (1) asyncio.TimeoutError not caught in mesh_api/auth.py -- aiohttp timeout may propagate as uncaught exception. (2) handlers/registration.py: error messages disclose exception details to users, FSM stores password in MemoryStorage. Both are out of scope for schedule-command feature, to be addressed in separate tasks.
Alternatives considered: Fix now -- rejected, these are in files not owned by this feature's tasks.

## Decision: Task 2+3 architectural review -- REQUIRES FIXES
Date: 2026-02-28
Context: Review of handlers/schedule.py (510 lines) and bot.py changes. Architecture is sound: router pattern, IDOR checks, callback_data format, ensure_token integration, MeshClient lifecycle all correct. However two REQUIRED fixes identified: (1) DRY -- three callback handlers are near-identical 35-line blocks, must extract shared function; (2) AuthenticationError swallowed in week fetch loop because it inherits MeshAPIError. One REQUIRED fix from security reviewer: html.escape() on API data rendered with parse_mode="HTML".
Alternatives considered: N/A -- review decision.

## Decision: Accept _fetch_day_schedule wrapper as dead code -- remove it
Date: 2026-02-28
Context: _fetch_day_schedule (lines 175-180) wraps a single client.get_schedule() call, adding no logic. It is used in _get_schedule_text but NOT in _fetch_week_schedule, which calls client.get_schedule() directly. This inconsistency is confusing. Decision: remove the wrapper, call client.get_schedule() directly in both places.
Alternatives considered: Keep wrapper and also use it in _fetch_week_schedule -- rejected, the wrapper adds no value.

## Decision: Task 2+3 RE-REVIEW -- APPROVED
Date: 2026-02-28
Context: All 5 fixes applied correctly. File reduced from 510 to 427 lines. (1) _handle_schedule_request extracted -- 3 callbacks now ~10 lines each, IDOR + token + fetch + error handling in one place. (2) html.escape() on all API data in _format_day_schedule. (3) AuthenticationError re-raised in week loop. (4) try/finally for callback.answer() in all 3 callbacks. (5) _fetch_day_schedule wrapper removed, client.get_schedule() called directly. Architecture is clean, consistent with project patterns, ready for tests.
Alternatives considered: N/A -- review decision.

## Decision: No FSM state for schedule navigation
Date: 2026-02-28
Context: All navigation state (child_id, period) stored in callback_data buttons. MemoryStorage loses state on restart. Callback_data persists in Telegram message buttons.
Alternatives considered: FSM with MemoryStorage (lost on restart), FSM with Redis storage (infrastructure overhead for a simple feature).
