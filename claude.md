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
.
├── bot.py, config.py
├── core/           — database.py, encryption.py
├── mesh_api/       — auth.py, client.py, endpoints.py, models.py, exceptions.py
├── handlers/       — start, registration, schedule, ocenki, dz, admin, quiz, settings, profile...
├── keyboards/      — main_menu.py, quiz_kb.py
├── middlewares/     — access.py (ACL), throttle.py (anti-spam)
├── llm/            — client.py, prompts.py, parser.py
├── services/       — test_generator, answer_checker, progress_tracker, notification_service, gamification
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
- Retry-очередь временных ошибок (v1.1.0): повторная обработка раз в 5 минут
- Монитор деградации МЭШ API (v1.1.0): алерт в `ADMIN_ID` при затяжных сбоях
- В `/profile` (v1.0.0): live-статус МЭШ API + fallback-сводка кеша

## Геймификация (v0.5.0)

- Сервис: `services/gamification.py` — XP, уровни, серии, значки, темы
- 5 тем: neutral, minecraft, ninjago, space, superhero (THEMES dict)
- 11 значков: BADGES dict
- Таблицы: `user_stats`, `achievements`, `daily_challenges` (миграция 005)
- CRUD: `database/crud.py` — get/ensure/update_user_stats, get/set_user_theme, get/award_badge и др.
- Выбор темы: `handlers/settings.py` (callback `settings:theme`, `theme:<key>`)
- Прогресс-бар + XP в `handlers/quiz.py`, заголовок в `handlers/history.py`
- Ежедневные задания: `handlers/language.py` (callback `daily_challenge`)
- Тесты: `tests/test_gamification.py` (46 тестов)

## Деплой на сервер

- **Сервер**: 45.152.113.91, SSH порт 4422
- **Пользователь**: `school_bot` (SSH-ключ: `~/.ssh/id_ed25519_rag`)
- **Путь**: `/opt/school_bot`
- **Python venv**: `/opt/school_bot/venv`
- **Systemd сервис**: `school_bot.service`
- **Управление**: `sudo systemctl restart school_bot` (sudoers настроен)

### Быстрый деплой (из локальной машины)

```bash
SSH_KEY="~/.ssh/id_ed25519_rag"
SSH="ssh -i $SSH_KEY -p 4422 school_bot@45.152.113.91"

# 1. Загрузить файлы
tar czf /tmp/school_bot.tar.gz --exclude=venv --exclude=data --exclude=.git --exclude=__pycache__ -C /path/to/repo .
scp -i "$SSH_KEY" -P 4422 /tmp/school_bot.tar.gz school_bot@45.152.113.91:/tmp/

# 2. Распаковать и обновить зависимости
$SSH "cd /opt/school_bot && tar xzf /tmp/school_bot.tar.gz && venv/bin/pip install -r requirements.txt"

# 3. Перезапустить бота
$SSH "sudo systemctl restart school_bot"

# 4. Проверить статус
$SSH "sudo systemctl status school_bot"
```

### Особенности серверной .env

- SSH-прокси отключен (бот на том же сервере, что и туннель)
- LLM Studio недоступен на сервере (квизы не работают без локального LLM)

## Важные детали

- Пароли МЭШ зашифрованы (Fernet), ключ в .env
- МЭШ API неофициальное — может сломаться
- Rate limit: ≤30 запросов/мин к МЭШ API
- Playwright: после pip install нужно `patchright install chromium`
- Авторизация МЭШ двухуровневая (HybridMeshAuth): curl_cffi → Playwright fallback
- SSH-туннель отключён с v0.6.1 (бот на сервере). Код остался в `bot.py` закомментированным. Для локальной разработки: включить `MESH_SSH_PROXY=true` в `.env` и раскомментировать блок в `main()`

## Аналитика оценок (v0.7.0)

- Сервис: `services/analytics.py` — парсинг оценок, средние по предметам, тренды, форматирование
- Хендлер: `handlers/analytics.py`, namespace `analytics:`
- Точка входа: кнопка «Аналитика» в клавиатуре оценок (`handlers/ocenki.py`)
- Периоды: неделя / месяц / четверть (сравнение с предыдущим аналогичным периодом)
- Данные: live из МЭШ API (не из grades_cache)
- Доступ: только parent/admin (как оценки)
- Тесты: `tests/test_analytics.py`

## Автономный режим — работа без подтверждений

В рамках этого проекта Claude выполняет все действия **без запроса подтверждения** у пользователя:

### Файлы и код
- Создание, редактирование, удаление любых файлов в папке проекта

### Git
- Все git-операции: add, commit, tag, push, pull, branch, merge и др.

### Командная строка
- Запуск любых команд bash/PowerShell: сборка, тесты, установка пакетов, SSH-команды

### Деплой
- Копирование файлов на сервер (scp), перезапуск сервиса, проверка статуса
- **Автодеплой**: если изменён код бота (.py) — автоматически задеплоить на сервер и перезапустить сервис после завершения задачи

### Зависимости
- Установка новых Python-пакетов (`pip install`), добавление в `requirements.txt`

### Агенты — проактивное использование

Claude **обязан** использовать агентов без запроса, когда задача этого требует:

| Ситуация | Агент/скилл | Когда запускать |
|----------|-------------|-----------------|
| Написание нового кода | `code-writing` | Всегда при создании/изменении логики |
| Код написан | `code-reviewing` | Автоматически после написания кода |
| Код работает с вводом, API, auth | `security-auditor` | Автоматически при изменении таких файлов |
| Нужно разобраться в коде | `Explore` агент | При исследовании незнакомых частей проекта |
| Планирование реализации | `Plan` агент | Перед началом сложной задачи |
| Подозрение на баги | `bug-finder` | При странном поведении или после крупных изменений |
| Несколько независимых задач | Параллельные `general-purpose` агенты | Когда задачи не зависят друг от друга |
| Тесты | `test-master` | При написании или проверке тестов |

### Попутные исправления
- Если при выполнении основной задачи замечен мелкий баг, опечатка, битый импорт — исправлять сразу, не спрашивая

### Единственное исключение
Действия, которые могут привести к **необратимой потере данных** (удаление базы данных на сервере, `rm -rf` критических директорий) — уточнить у пользователя.
