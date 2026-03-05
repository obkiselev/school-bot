# Инструкции для Claude — School Bot

> Общие правила (версионирование, git, фиксация результатов) — см. глобальный CLAUDE.md.
> Здесь только специфика проекта.

## Агенты — информирование пользователя

При запуске агентов обязательно сообщи пользователю: какой агент, зачем, результат.

## О проекте

- **Название**: School Bot — единый школьный Telegram-бот
- **Язык**: Python 3.9+
- **Фреймворк**: aiogram 3.25 (асинхронный)
- **БД**: SQLite через aiosqlite
- **Конфигурация**: pydantic-settings + .env
- **Шифрование**: cryptography (Fernet)
- **LLM**: LM Studio (OpenAI-совместимый API, localhost:1234)

## Ролевая система

- **admin** — полный доступ + управление пользователями
- **parent** — полный доступ (без управления пользователями)
- **student** — ограниченный: расписание, ДЗ, тесты (без оценок)
- Доступ через админа (`/allow <id> role`), главный админ (ADMIN_ID) неудаляем
- Клавиатуры: `full_menu_keyboard()` (admin/parent), `student_menu_keyboard()` (student)

## Структура проекта

```
school_bot/
├── bot.py, config.py
├── core/           — database.py, encryption.py
├── mesh_api/       — auth.py, client.py, endpoints.py, models.py, exceptions.py
├── handlers/       — start, registration, schedule, ocenki, dz, admin, quiz, settings, profile...
├── keyboards/      — main_menu.py, quiz_kb.py
├── middlewares/     — access.py (ACL), throttle.py (anti-spam)
├── llm/            — client.py, prompts.py, parser.py
├── services/       — test_generator, answer_checker, progress_tracker, notification_service
├── states/         — registration.py, quiz_states.py
├── database/       — crud.py, migrations/
├── utils/          — token_manager.py, rate_limiter.py
└── data/           — SQLite БД, логи
```

## Навигация

- Кнопка «🏠 Главное меню» — `home_button()` в `keyboards/main_menu.py`
- Callback `go_home` в `handlers/start.py` — очищает FSM, меню по роли
- Оценки: `handlers/ocenki.py`, namespace `ocenki:`
- ДЗ: `handlers/dz.py`, namespace `dz:`
- Оба используют `profile_id` из `users.mesh_profile_id`

## Уведомления

- APScheduler в event loop aiogram (`bot.py`)
- Оценки: 18:00, ДЗ: 19:00 (настройки в .env)
- Сервис: `services/notification_service.py`
- Кеш: таблицы `grades_cache`, `homework_cache` с `is_notified`
- Таблица `notification_runs` — отслеживание последнего запуска каждого типа
- `check_and_send_missed(bot)` — при старте досылает пропущенные (бот был выключен в 18:00/19:00)
- `misfire_grace_time=3600`, `coalesce=True` — APScheduler запустит задание до 1 ч после пропуска
- Rate limit: 2.5 сек между пользователями
- TelegramForbiddenError → автоотключение уведомлений
- `mark_*_notified()` вызывается ТОЛЬКО при успешной отправке (защита от потери данных)

## Важные детали

- Пароли МЭШ зашифрованы (Fernet), ключ в .env
- МЭШ API неофициальное — может сломаться
- Rate limit: ≤30 запросов/мин к МЭШ API
- Playwright: после pip install нужно `patchright install chromium`
- Авторизация МЭШ двухуровневая (HybridMeshAuth): curl_cffi → Playwright fallback
