# School Bot — Прогресс разработки

## Текущая версия: 1.3.0

## Статус: LLM-мост

---

## Ближайший план (v1.4.0)

- [ ] Таблица лидеров по XP среди учеников
- [ ] Еженедельные челленджи
- [ ] Достижения за регулярность (30 дней и т.д.)
- [ ] Обмен результатами между учениками

---

## Общая картина проекта

**school_bot** — единый школьный Telegram-бот для родителей и учеников:

- **Родители** (role=parent): все функции — расписание, оценки, ДЗ, тесты через МЭШ API + AI
- **Ученики** (role=student): расписание, ДЗ, тесты (без оценок) через МЭШ API + AI
- **Админ** (role=admin): все функции + управление пользователями (/allow, /block, /users)

Доступ только через админа. Бот определяет роль пользователя и показывает соответствующее меню.

---

## Фаза 1: Фундамент — ЗАВЕРШЕНА

- [x] Структура проекта (модули: core, mesh_api, handlers, keyboards, states, database, notifications, utils)
- [x] Конфигурация через pydantic-settings + .env
- [x] База данных SQLite (aiosqlite) — инициализация, CRUD
- [x] Шифрование паролей (Fernet)
- [x] МЭШ API клиент через OctoDiary (auth, client, endpoints, models, exceptions)
- [x] Регистрация пользователей через FSM (логин → пароль → SMS-код → выбор детей)
- [x] Команда /start
- [x] Точка входа bot.py с polling

## Фаза 2: Основные команды — ЗАВЕРШЕНА

- [x] /raspisanie — расписание уроков (сегодня/завтра/неделя)
- [x] Автоматическое обновление токена МЭШ (utils/token_manager.py)
- [x] Inline-кнопки переключения периода
- [x] Выбор ребёнка при нескольких детях
- [x] IDOR-защита (проверка владельца student_id)
- [x] HTML-экранирование данных МЭШ API
- [x] Обработка ошибок МЭШ API с кнопкой «Повторить»
- [x] Unit-тесты для расписания (30 тестов, 100% pass) → 72 теста (v0.4.3)
- [x] Слияние school_helper: ролевая система (admin/parent/student)
- [x] Слияние school_helper: Access Control Middleware
- [x] Слияние school_helper: тестирование по языкам (English, Spanish) через LLM
- [x] Слияние school_helper: история тестов и статистика
- [x] Слияние school_helper: админ-команды (/allow, /block, /users)
- [x] Прокси для Telegram Bot API (AiohttpSession + SOCKS5)
- [x] Навигация: кнопка «Главное меню» во всех разделах бота
- [x] /ocenki — оценки с фильтрацией по датам (сегодня/неделя/месяц)
- [x] /dz — домашние задания (сегодня/завтра/неделя)

## Фаза 3: Уведомления — ЗАВЕРШЕНА

- [x] APScheduler setup (AsyncIOScheduler, CronTrigger, интеграция в bot.py)
- [x] Ежедневные уведомления (18:00 — оценки, 19:00 — ДЗ)
- [x] /settings — настройка уведомлений (inline-кнопки вкл/выкл)
- [x] Кеширование для определения новых оценок (grades_cache, homework_cache с is_notified)
- [x] Кнопка «Настройки» в главном меню (admin, parent, student)
- [x] Очистка старого кеша (еженедельно, воскресенье 03:00)
- [x] Обработка ошибок: TelegramForbiddenError → отключение уведомлений, rate limit МЭШ API
- [x] Устойчивые уведомления: досылка пропущенных при рестарте бота (v0.4.3)

## Фаза 4: Production — ЗАВЕРШЕНА

- [x] Логирование (RotatingFileHandler) — реализовано в v0.2.3
- [x] Rate limiting — глобальный token-bucket для МЭШ API + per-user throttle middleware
- [x] /help — справка по командам (по роли)
- [x] /profile — профиль пользователя (маскировка логина, дети, роль)
- [x] Баг-фикс: get_user() теперь возвращает role и is_blocked
- [x] Баг-фикс: исправлены тесты TokenManager (MeshClient → MeshAuth)
- [x] Баг-фикс: регистрация ученических аккаунтов (403 на profile_info → fallback через session_info)
- [~] Баг-фикс: ошибка 499/E0002 при регистрации ученика — каскад fallback-ов (get_user_info → get_student_profiles)
- [x] Деплой на VPS (45.152.113.91, systemd, пользователь school_bot)

## Фаза 5: Геймификация — ЗАВЕРШЕНА

- [x] Миграция 005: таблицы user_stats, achievements, daily_challenges
- [x] Сервис геймификации (`services/gamification.py`): XP, уровни, серии, значки, 5 тем оформления
- [x] 5 тем: Нейтральный, Minecraft, Ninjago, Космос, Супергерой
- [x] XP-система: +10/правильный, +20 за 100%, +5*streak (макс +50), +5 за быстрый ответ
- [x] Уровни: `level = 1 + floor(sqrt(xp/100))`
- [x] 11 значков/достижений (first_quiz, perfect_score, streak_3/7/30, tests_10/50, level_5, speed_demon, polyglot, explorer)
- [x] Серии (streaks): ежедневные квизы продляют серию, пропуск = сброс
- [x] Прогресс-бар в тесте (заголовок вопроса с процентом)
- [x] Тематизированные результаты теста (сообщения, эмодзи, названия уровней по теме)
- [x] Выбор темы в настройках (`handlers/settings.py`)
- [x] Геймификация в истории тестов (`handlers/history.py`)
- [x] Ежедневные задания — кнопка в меню тестов, авто-генерация из слабых тем
- [x] CRUD для user_stats, achievements, daily_challenges (`database/crud.py`)
- [x] 46 тестов геймификации (118 всего, 100% pass)

## Фаза 6: Адаптивная сложность — ЗАВЕРШЕНА

- [x] `services/level_adapter.py` (NEW) — extract_grade, grade_to_language_level, get_user_level
- [x] `tests/test_level_adapter.py` (NEW) — 27 тестов
- [x] `config.py` — TOPICS вложенные по уровням (A1/A2/B1/B2/C1), LEVEL_DESCRIPTIONS по CEFR
- [x] `states/quiz_states.py` — новое состояние choosing_level
- [x] `keyboards/quiz_kb.py` — level_keyboard(), topic_keyboard(language, level)
- [x] `handlers/language.py` — ученик -> авто-уровень, родитель/админ -> выбор уровня
- [x] `handlers/topic.py` — темы по уровню
- [x] `llm/prompts.py` — убран хардкод "5th-grade", динамический уровень CEFR
- [x] `services/test_generator.py` — параметр level
- [x] `handlers/quiz_settings.py` — передача level в генератор, уровень в UI
- [x] `database/migrations/006_adaptive_difficulty.sql` (NEW) — колонка difficulty в test_sessions
- [x] `core/database.py` — миграция 006
- [x] `database/crud.py` — difficulty в save_test_session
- [x] `handlers/quiz.py` — сохранение difficulty в результатах

## Фаза 7: Аналитика оценок — ЗАВЕРШЕНА

- [x] `services/analytics.py` (NEW) — парсинг оценок, средние по предметам, тренды, распределение, форматирование
- [x] `handlers/analytics.py` (NEW) — Telegram-хендлер с callbacks, IDOR-проверкой, обработкой ошибок
- [x] `tests/test_analytics.py` (NEW) — 48 тестов: парсинг, средние, тренды, распределение, периоды, форматирование
- [x] Кнопка «Аналитика» в клавиатуре оценок (`handlers/ocenki.py`)
- [x] Регистрация analytics router в `bot.py`
- [x] 3 периода: неделя / месяц / четверть — сравнение с предыдущим аналогичным периодом
- [x] Тренды: рост/падение/стабильно (порог ±0.3)
- [x] Распределение оценок (5/4/3/2 с процентами)
- [x] Лучший и худший предмет
- [x] Автономный режим добавлен в CLAUDE.md проекта

---

## Известные баги и проблемы

- МЭШ API через OctoDiary — при обновлении библиотеки могут сломаться типы данных
- mos.ru может обнаружить автоматизацию и сбросить пароль (v0.2.2 снижает риск)
- Для LLM-моста нужен защищённый HTTPS endpoint и токен
- **curl_cffi TLS таймаут через SSH-туннель**: TCP pre-check прокси проходит (OK), но TLS-соединение с mos.ru зависает 15с и отваливается. Возможные причины: SSH-сервер блокирует HTTPS к mos.ru, mos.ru блокирует IP сервера, или MTU/фрагментация мешает TLS-handshake. Пока обходим через Playwright fallback.
- **Playwright: после установки patchright нужно скачать браузер** — выполнить `patchright install chromium` (иначе ошибка "Executable doesn't exist")

---

## Changelog

### v1.3.0 — Стабильный релиз (этап): Health + CI

**Мониторинг (`services/health_check.py`, `handlers/admin.py`):**
- Добавлен админский `/health` с проверкой:
  - доступности БД (`SELECT 1`)
  - доступности LLM-targets (bridge/direct) через `/models`
- В сообщении отображается детальный статус по каждому target

**Интеграция в команды (`handlers/start.py`, `README.md`):**
- `/health` добавлен в меню команд admin
- `/health` добавлен в `/help` для admin
- Обновлена таблица команд в README
- Для схемы `bridge + tunnel` вывод `/health` теперь не помечает `direct localhost` как ошибку, если `bridge` уже доступен (показывается как ожидаемый резерв)

**CI/CD (`.github/workflows/ci.yml`):**
- Добавлен GitHub Actions workflow:
  - запуск на `push`/`pull_request` в `main`
  - установка Python 3.11 и зависимостей
  - прогон `pytest tests -q`

### v1.2.2 — Явная диагностика режима генерации тестов

**Режим генерации в UI (`handlers/quiz_settings.py`):**
- Бот показывает `ℹ️ Режим: LLM` или `ℹ️ Режим: fallback`
- Для fallback добавляется краткая причина (`Причина: ...`)

**Источник/причина генерации (`services/test_generator.py`, `llm/client.py`):**
- Каждому вопросу проставляется технический маркер источника: `_source` (`llm` / `fallback`)
- Для fallback передаётся `_source_reason` (последняя ошибка endpoint)
- В LLM-клиент добавлен трекер последней ошибки `get_last_llm_error()`

**Эксплуатационные заметки (документация):**
- Обновлены `README.md`, `CLAUDE.md`, `readme.txt`
- Зафиксировано, что на VPS `LLM_BASE_URL=http://localhost:1234/v1` без локально поднятого LM Studio приводит к ожидаемому fallback
- Тайм-аут LLM зафиксирован как `LLM_REQUEST_TIMEOUT=120`

### v1.2.1 — LLM-мост: bridge -> direct -> fallback

**Конфиг и клиент (`config.py`, `llm/client.py`):**
- Добавлены параметры `LLM_BRIDGE_URL`, `LLM_API_KEY`, `LLM_REQUEST_TIMEOUT`, `LLM_FALLBACK_ENABLED`
- Клиент LLM теперь работает по цепочке:
  1. `LLM_BRIDGE_URL` (рекомендуемый защищённый канал)
  2. `LLM_BASE_URL` (direct endpoint, например localhost)
  3. fallback-генерация тестов в приложении

**Fallback-режим (`services/fallback_test_generator.py`, `services/test_generator.py`):**
- Добавлен шаблонный генератор вопросов для English/Spanish
- При недоступности LLM бот продолжает выдавать тесты вместо полной ошибки

**Bridge-сервис (`llm_bridge/server.py`):**
- Добавлен отдельный локальный aiohttp-сервис с `Bearer`-проверкой
- Проксирование OpenAI-совместимых запросов `/v1/*` в LM Studio (`LLM_UPSTREAM_BASE_URL`)
- `/health` endpoint для проверок
- Инструкции запуска: `llm_bridge/README.md`

### v1.2.0 — Напоминания и планировщик

**Планировщик напоминаний (`services/notification_service.py`):**
- Добавлена ежедневная вечерняя задача `daily_planner_reminders` (по умолчанию в `20:00`)
- Напоминание за день до контрольных/проверочных (анализ расписания на завтра)
- Напоминание о ДЗ со сроком на завтра (вечерняя проверка)
- Добавлена обработка пропущенного запуска `planner` после рестарта (`check_and_send_missed`)

**Личные напоминания (`/remind`):**
- Новый хендлер `handlers/reminders.py`
- Команды:
  - `/remind list` — список напоминаний
  - `/remind add HH:MM Текст` — добавить ежедневное напоминание
  - `/remind del ID` — удалить напоминание
- Фоновая задача `custom_reminders_processor` запускается каждую минуту и отправляет due-напоминания

**База данных:**
- Новая таблица `custom_reminders` (миграция `007_reminders.sql`)
- В `database/crud.py` добавлены CRUD-функции для пользовательских напоминаний

**Команды и конфиг:**
- В меню команд и `/help` добавлена команда `/remind`
- В `config.py` и `.env.example` добавлен `REMINDER_NOTIFICATION_TIME`

### v1.1.0 — Устойчивость к сбоям (этап 3): retry-очередь + алерт админу

**Уведомления (`services/notification_service.py`):**
- Добавлена retry-очередь для временных ошибок отправки/МЭШ API:
  - периодическая обработка очереди (`retry_queue_processor`)
  - экспоненциальная задержка между попытками
  - ограничение числа повторов и удаление из очереди при успехе/без изменений
- Добавлен мониторинг недоступности МЭШ API:
  - анализ доли API-ошибок по запуску
  - счётчик подряд проблемных запусков
  - автоматический алерт в `ADMIN_ID` при длительной деградации
- Логирование усилено:
  - явные причины постановки в retry
  - события очереди (повтор/исчерпаны попытки/успех)
  - события деградации и восстановления API

### v1.0.0 — Устойчивость к сбоям (этап 2): статус МЭШ API в профиле + fallback на кеш

**Профиль пользователя (`/profile`):**
- Добавлена live-проверка доступности МЭШ API (короткий запрос с таймаутом)
- В профиль выведен статус:
  - `МЭШ API: ✅ доступен`
  - `МЭШ API: ❌ недоступен (показываются данные из кеша)`
- При недоступности API выводится сводка кеша по пользователю:
  - количество кешированных оценок + время последнего обновления
  - количество кешированных ДЗ + время последнего обновления

**Новые/изменённые части:**
- `handlers/profile.py` — health-check API + отображение fallback-сводки
- `database/crud.py` — `get_user_cache_summary(user_id)` для агрегатов кеша
- `README.md`, `readme.txt`, `PROGRESS.md` — обновление версии и описания

### v0.9.0 — Устойчивость к сбоям (этап 1): надёжная обработка уведомлений

**Уведомления (services/notification_service.py):**
- Добавлены явные статусы обработки пользователя: `sent` / `no_changes` / `failed`
- Итоговые логи рассылки приведены к операционной метрике:
  - `Отправлено X из Y, без изменений: N, ошибок: Z`
- Усилено логирование причин неотправки:
  - пустой токен, отсутствие profile_id, отсутствие детей
  - ошибки МЭШ API при обработке ДЗ
  - неудачная отправка после retry
- Поведение пометки `mark_*_notified()` сохранено безопасным:
  - запись помечается как отправленная только после успешной доставки в Telegram

**Тесты:**
- `tests/test_notifications.py` — 25/25 pass
- Полный набор: `193 passed`

### v0.8.0 — Стабилизация: устранение тихих ошибок и улучшение логирования

**Исправления стабильности (Приоритет 1):**
- Убраны оставшиеся `except ...: pass` в критичных местах и добавлено диагностическое логирование
- Улучшена наблюдаемость ошибок в browser auth (Playwright): ожидание SMS, поиск input, fallback submit
- Улучшено логирование в регистрации: ошибки обновления inline-клавиатуры больше не теряются
- Улучшено логирование для `daily_challenge` при сбоях БД
- Поднят уровень логов для пропусков миграций 002/003 с `debug` до `warning`
- Добавлен debug-лог ошибок JSON-парсинга LLM-ответа

**Изменённые файлы:**
- `handlers/registration.py`
- `database/crud.py`
- `llm/parser.py`
- `mesh_api/playwright_auth.py`
- `core/database.py`
- `README.md`
- `readme.txt`
- `PROGRESS.md`

### v0.7.0 — Аналитика оценок: средний балл, тренды, распределение

**Аналитика оценок:**
- Средний балл по каждому предмету (нечисловые "зачет"/"н" пропускаются)
- Тренды: сравнение текущего периода с предыдущим (рост/падение/стабильно, порог ±0.3)
- Распределение оценок: 5/4/3/2 с количеством и процентами
- Лучший и худший предмет
- 3 периода: неделя (7 дн) / месяц (30 дн) / четверть (90 дн)
- Данные live из МЭШ API (2 вызова: текущий + предыдущий период)
- Доступ: только parent/admin
- Точка входа: кнопка «Аналитика» в клавиатуре оценок

**Автономный режим:**
- Добавлен раздел в CLAUDE.md проекта — работа без подтверждений (файлы, git, bash, деплой, агенты)

**Тесты (193 всего, 100% pass):**
- `tests/test_analytics.py` (48 тестов) — парсинг, средние, тренды, распределение, периоды, форматирование

**Новые файлы:**
- `services/analytics.py` — ядро аналитики
- `handlers/analytics.py` — Telegram-хендлер
- `tests/test_analytics.py` — 48 тестов

**Изменённые файлы:**
- `handlers/ocenki.py` — кнопка «Аналитика» в клавиатуре периодов
- `bot.py` — регистрация analytics router
- `CLAUDE.md` — аналитика + автономный режим
- `README.md` — версия, новая фича, структура
- `PROGRESS.md` — Phase 7, changelog

### v0.6.1 — Деплой на сервер, отключение SSH-туннеля

**Деплой:**
- Бот задеплоен на VPS 45.152.113.91 в `/opt/school_bot`
- Пользователь `school_bot`, Python 3.12.3 venv, systemd сервис
- `sudo systemctl restart school_bot` — перезапуск бота
- Инструкции деплоя добавлены в CLAUDE.md

**SSH-туннель отключён:**
- Бот на сервере — туннель больше не нужен
- `bot.py`: вызовы `_start_ssh_tunnel()` и `_monitor_ssh_tunnel()` закомментированы
- `.env`: SSH-настройки закомментированы
- Код туннеля сохранён для локальной разработки (раскомментировать при необходимости)

**Изменённые файлы:**
- `bot.py` — закомментирован запуск SSH-туннеля в `main()`
- `.env` — SSH-настройки закомментированы
- `.env.example` — обновлены комментарии
- `CLAUDE.md` — добавлен раздел "Деплой на сервер", пометка об SSH-туннеле

### v0.6.0 — Адаптивная сложность: CEFR-уровни, авто-определение для учеников

**Адаптивная сложность тестов:**
- Ученики: уровень определяется автоматически из class_name (например, "5A" -> класс 5 -> A2 English)
- Родители/админы: ручной выбор уровня (A1/A2/B1/B2/C1) через инлайн-клавиатуру
- Маппинг класс→уровень: English (1-4→A1, 5-6→A2, 7-8→B1, 9-11→B2), Spanish (1-6→A1, 7-8→A1-A2, 9-11→A2)

**Темы по уровням:**
- TOPICS реструктурированы из плоского списка в вложенные по CEFR: `{"English": {"A1": [...], "A2": [...], ...}}`
- English: 5 уровней (A1-C1), по 5 тем на каждый
- Spanish: 4 уровня (A1, A1-A2, A2, B1), по 5 тем на каждый

**LLM промпт:**
- Убран хардкод "5th-grade student" — теперь динамический уровень CEFR с описанием
- Генерация тестов учитывает уровень студента

**БД:**
- Миграция 006: колонка `difficulty` в `test_sessions` — сохраняет CEFR-уровень каждого теста

**Тесты (145 всего, 100% pass):**
- `tests/test_level_adapter.py` (27 тестов) — extract_grade, grade_to_language_level, AVAILABLE_LEVELS, get_user_level

**Новые файлы:**
- `services/level_adapter.py` — ядро: extract_grade, grade_to_language_level, get_user_level
- `database/migrations/006_adaptive_difficulty.sql` — миграция
- `tests/test_level_adapter.py` — 27 тестов

**Изменённые файлы:**
- `config.py` — TOPICS по уровням, LEVEL_DESCRIPTIONS по CEFR
- `states/quiz_states.py` — состояние choosing_level
- `keyboards/quiz_kb.py` — level_keyboard(), topic_keyboard(language, level)
- `handlers/language.py` — авто-определение уровня (student) / выбор (parent/admin)
- `handlers/topic.py` — темы по уровню из FSM
- `llm/prompts.py` — динамический уровень в промпте
- `services/test_generator.py` — параметр level
- `handlers/quiz_settings.py` — передача level, отображение в UI
- `handlers/quiz.py` — difficulty в save_test_session
- `database/crud.py` — difficulty параметр
- `core/database.py` — миграция 006

### v0.5.0 — Геймификация: XP, уровни, серии, значки, 5 тем оформления

**Новая система геймификации (Duolingo-стиль):**
- `services/gamification.py` — ядро: XP-расчёт, уровни, серии, значки, тематизация
- 5 тем оформления: Нейтральный, Minecraft, Ninjago, Космос, Супергерой
- Каждая тема: уникальные названия уровней, эмодзи, сообщения, валюта XP
- XP-система: +10 за правильный, +20 за 100%, +5*streak (макс +50), +5 за быстрый ответ (<10 сек)
- Уровни: `level = 1 + floor(sqrt(xp/100))` (Level 2 = 100 XP, Level 5 = 1600 XP)
- 11 значков: first_quiz, perfect_score, streak_3/7/30, tests_10/50, level_5, speed_demon, polyglot, explorer
- Серии (streaks): ежедневные квизы = продление, пропуск дня = сброс к 1

**Тематизированный вывод:**
- Прогресс-бар в заголовке каждого вопроса (вопрос X/Y, % правильных)
- Тематизированные сообщения при правильном/неправильном ответе
- Экран результатов с XP, серией, уровнем, прогресс-баром, новыми значками
- Геймификация в истории тестов (заголовок со статистикой)

**Ежедневные задания:**
- Кнопка "Задание дня" в меню тестов
- Авто-генерация из слабых тем (или дефолт English/General Vocabulary)
- +50 XP за выполнение

**Выбор темы:**
- Кнопка "Тема оформления" в настройках
- Инлайн-клавиатура с галочкой на текущей теме

**БД:**
- Миграция 005: таблицы user_stats, achievements, daily_challenges
- 12 новых CRUD-функций в database/crud.py

**Тесты (118 всего, 100% pass):**
- `tests/test_gamification.py` (46 тестов) — уровни, XP, серии, значки, темы, форматирование

**Новые файлы:**
- `services/gamification.py` — ядро геймификации
- `database/migrations/005_gamification.sql` — миграция
- `tests/test_gamification.py` — 46 тестов

**Изменённые файлы:**
- `core/database.py` — запуск миграции 005
- `database/crud.py` — CRUD для user_stats, achievements, daily_challenges
- `handlers/quiz.py` — прогресс-бар, тематизированные ответы, начисление XP
- `handlers/quiz_settings.py` — загрузка темы пользователя
- `handlers/settings.py` — выбор темы оформления
- `handlers/history.py` — геймификационный заголовок
- `handlers/language.py` — обработчик ежедневных заданий
- `keyboards/main_menu.py` — кнопка "Задание дня"

### v0.4.3 — Устойчивые уведомления + тестовое покрытие

**Устойчивые уведомления (была v0.4.1-plan, теперь реализовано):**
- Новая таблица `notification_runs` — отслеживание даты последней успешной рассылки
- `check_and_send_missed(bot)` — при старте бота досылает пропущенные уведомления (бот был выключен в 18:00/19:00)
- `save_notification_run()` / `get_last_notification_run()` — CRUD для таблицы
- APScheduler: `misfire_grace_time=3600`, `coalesce=True` — запуск до 1 часа после пропуска
- Миграция 004 для существующих БД (CREATE TABLE IF NOT EXISTS)

**Фикс потери данных:**
- `mark_grades_notified()` и `mark_homework_notified()` теперь вызываются ТОЛЬКО при успешной отправке (`_safe_send_message() == True`)
- Раньше: ошибка отправки → оценки/ДЗ помечались как отправленные → данные терялись навсегда
- `_cleanup_stale_cache_on_start()` теперь помечает только записи старше 2 дней (раньше — все, уничтожая свежие данные)

**Тестовое покрытие (72 теста, 100% pass):**
- `tests/test_notifications.py` (22 теста) — форматирование, retry, check_and_send_missed, CRUD, mark-on-success
- `tests/test_rate_limiter.py` (6 тестов) — token bucket: burst, exhaustion, refill, cap, concurrent
- `tests/test_access.py` (11 тестов) — ACL middleware: admin bypass, public commands, FSM bypass, fail-closed
- Ранее: 36 тестов (schedule + token manager) → теперь 72 теста

**Изменённые файлы:**
- `database/migrations/init.sql` — таблица notification_runs
- `core/database.py` — миграция 004
- `database/crud.py` — save_notification_run, get_last_notification_run
- `services/notification_service.py` — check_and_send_missed, mark-on-success, misfire_grace_time, stale cache fix
- `bot.py` — вызов check_and_send_missed при старте
- `tests/test_notifications.py` (новый)
- `tests/test_rate_limiter.py` (новый)
- `tests/test_access.py` (новый)

### v0.4.2 — Стабилизация: логирование, retry уведомлений, race conditions, валидация

**Логирование тихих ошибок (Приоритет 1):**
- Заменены 26 `except: pass` на `except Exception as e: logger.warning/debug(...)` в 10 файлах
- Критичное: `handlers/quiz.py` — результат теста не сохранялся молча, теперь logger.error
- Миграции БД, прокси, SSH, Playwright, access middleware — все ошибки теперь видны в логах

**Уведомления (Приоритет 2):**
- `_safe_send_message()` — retry (3 попытки, 3 сек между) для временных ошибок сети
- `_safe_send_message()` возвращает `bool` для подсчёта реально доставленных сообщений
- Очистка кеша при старте бота — `is_notified=0` записи помечаются как доставленные (предотвращает повторную рассылку)

**Race conditions (Приоритет 3):**
- Per-user `asyncio.Lock` для авторизации — два одновременных `start_login` больше невозможны
- `is_auth_in_progress()` — бот отвечает "авторизация уже идёт" при повторном нажатии

**Валидация конфигурации (Приоритет 5):**
- `@field_validator` для `GRADES_NOTIFICATION_TIME` и `HOMEWORK_NOTIFICATION_TIME` (формат HH:MM, час 0-23, минуты 0-59)
- `@field_validator` для `TIMEZONE` (проверка через `pytz.timezone()`)
- Невалидная конфигурация → ошибка при запуске бота, а не в рантайме

**Ресурсы Playwright (Приоритет 6):**
- `_close_browser()` — отменяет зависший Future `_auth_complete`
- `_close_browser()` — удаляет обработчик `response` перед закрытием страницы
- `_pending_auth` хранит timestamp — сессии старше 5 мин автоматически истекают
- `set_pending_auth()` / `get_pending_auth()` — безопасный доступ вместо прямого `_pending_auth[uid]`

**Изменённые файлы:**
- `config.py` — валидаторы времени и timezone
- `mesh_api/auth.py` — per-user lock, pending auth с TTL, set/get_pending_auth
- `handlers/registration.py` — async with lock, is_auth_in_progress
- `services/notification_service.py` — retry, кеш при старте
- `mesh_api/playwright_auth.py` — очистка Future, response listener
- `bot.py`, `core/database.py`, `handlers/quiz.py`, `handlers/start.py`, `mesh_api/client.py`, `middlewares/access.py`, `llm/client.py` — логирование ошибок

### v0.4.1 — Кнопка «Назад» в навигации оценок, ДЗ и расписания

(реализовано ранее, см. коммит fd94141)

### v0.4.0.1 — Фикс: 499/E0002 при регистрации ученика (каскад fallback-ов)

**Проблема:** При регистрации ученического аккаунта МЭШ `get_user_info()` (`school.mos.ru/v3/userinfo`) стал возвращать 499 с кодом E0002.

**Решение:**
- Добавлен каскад fallback-ов в `_finalize_profile_and_children()`:
  1. `get_users_profile_info()` — основной (для родителей)
  2. `get_user_info()` — первый fallback (school.mos.ru/v3/userinfo)
  3. `get_student_profiles()` — **новый** второй fallback (другой эндпоинт API)
- `_build_student_child()` принимает кешированный `StudentProfile` из fallback — без повторного вызова API
- Сообщение об ошибке упрощено (без технических деталей)

**Статус:** Код готов, ожидает проверки при регистрации ученика (вторая ошибка "страница не загрузилась" — временная недоступность сервера МЭШ, не баг кода).

**Изменённые файлы:**
- `mesh_api/auth.py` — каскад fallback, обновлён `_build_student_child()`

### v0.4.0 — Фикс: 401 при регистрации ученика (get_user_info вместо get_session_info)

**Проблема:** При регистрации ученического аккаунта МЭШ fallback `get_session_info()` возвращал 401 — эндпоинт `dnevnik.mos.ru/lms/api/sessions` не принимает `mesh_access_token`.

**Причина:** `mesh_access_token` выдан `school.mos.ru`, но `get_session_info()` обращается к `dnevnik.mos.ru` — другой домен, другая сессия. Через Playwright `mos_access_token` недоступен (серверный обмен).

**Решение:**
- Заменён `get_session_info()` (dnevnik.mos.ru) на `get_user_info()` (school.mos.ru/v3/userinfo)
- `get_user_info()` принимает `mesh_access_token` (тот же домен) и возвращает profile_id, имя, роли
- `_build_student_child()` обновлён для работы с UserInfo вместо SessionUserInfo

**Изменённые файлы:**
- `mesh_api/auth.py` — fallback через `get_user_info()`, обновлён `_build_student_child()`
- `mesh_api/playwright_auth.py` — убрана передача mos_access_token (не нужен)
- OctoDiary `async_.py` — откачен патч mos_access_token (не используется)

### v0.3.9 — Фикс: fallback на AsyncWebAPI для ученических аккаунтов

**Проблема:** Fallback v0.3.8 вызывал `get_session_info()` и `get_student_profiles()` на `AsyncMobileAPI`, но эти методы существуют только в `AsyncWebAPI`. Ученики получали: `'AsyncMobileAPI' object has no attribute 'get_session_info'`.

**Решение:**
- Хелпер `_make_web_api()` — создаёт `AsyncWebAPI` с тем же токеном и прокси
- Fallback `get_session_info()` → вызов через `AsyncWebAPI`
- Fallback `get_student_profiles()` → вызов через `AsyncWebAPI`

**Изменённые файлы:**
- `mesh_api/auth.py` — добавлен `_make_web_api()`, исправлены 2 вызова fallback-методов

### v0.3.8 — Фикс: регистрация ученических аккаунтов МЭШ (403 access_denied)

**Проблема:** При регистрации ребёнка (ученический аккаунт mos.ru) эндпоинт `profile_info` возвращал 403 — доступен только для родителей/учителей.

**Решение:**
- Общая функция `_finalize_profile_and_children()` — fallback-логика для всех путей авторизации
- При 403 на `get_users_profile_info()` → `get_session_info()` (работает для всех типов аккаунтов)
- При 403 на `get_family_profile()` → `get_student_profiles()` + данные из сессии
- Автоматический выбор профиля для ученика (пропуск шага "выберите детей")
- Нормализация ролей: поддержка как "StudentProfile", так и "student"

**Изменённые файлы:**
- `mesh_api/auth.py` — `_finalize_profile_and_children()`, `_build_student_child()`, рефакторинг `_finalize_auth()`
- `mesh_api/playwright_auth.py` — переход на общую функцию (убрана дупликация)
- `mesh_api/client.py` — `get_profile()` использует общую функцию + расширен маппинг ролей
- `handlers/registration.py` — `_save_registration()` (вынесена общая логика), авто-выбор для ученика

### v0.3.7 — Очистка: удаление school_helper, организация файлов

- Перенесён старый проект `school_helper` в `E:\backup_old\school_helper` (временный бэкап наработок)
- Отладочные скриншоты Playwright (debug_*.png, test_*.png) перенесены из `data/` в `tests/screenshots/`
- Папка `data/` содержит только runtime-данные (БД, логи)

### v0.3.6 — Фаза 4: Rate limiting + /help + /profile + баг-фиксы

**Rate Limiting (два уровня):**
- Глобальный token-bucket для МЭШ API (`utils/rate_limiter.py`) — 30 запросов/мин, позволяет burst
- Per-user throttle middleware (`middlewares/throttle.py`) — 2 сек между запросами, защита от спама
- ADMIN_ID и активные FSM-состояния — без ограничений
- Ручные `asyncio.sleep(2.5)` в notification_service.py заменены на централизованный лимитер

**Команда /help:**
- Справка по доступным командам в зависимости от роли (admin/parent/student)
- Для неавторизованных пользователей — минимальная справка
- Кнопка «Главное меню» для возврата

**Команда /profile:**
- Профиль пользователя: имя, username, ID, роль, дата регистрации
- Логин МЭШ замаскирован (`us***@example.com`)
- Список привязанных детей с классами
- Кнопка «Профиль» в главном меню (inline, рядом с настройками)
- Команда `/profile` в Telegram Menu для всех ролей

**Баг-фиксы:**
- `get_user()` теперь возвращает `role` и `is_blocked` — добавлены в SELECT
- Тесты TokenManager: `MeshClient` → `MeshAuth` (правильный мок), `authenticate` → `start_login`
- Тесты schedule handler: обновлены проверки текста ошибок под реальные сообщения
- 30 тестов — все проходят

**Новые файлы:**
- `utils/rate_limiter.py` — глобальный async token-bucket rate limiter
- `middlewares/throttle.py` — per-user flood control middleware
- `handlers/profile.py` — обработчик /profile + callback menu:profile

**Изменённые файлы:**
- `mesh_api/client.py` — `await mesh_api_limiter.acquire()` перед каждым API-вызовом
- `services/notification_service.py` — удалены ручные `asyncio.sleep(2.5)`
- `bot.py` — регистрация ThrottleMiddleware и profile router
- `handlers/start.py` — добавлен cmd_help + /profile в _set_user_commands
- `keyboards/main_menu.py` — кнопка «Профиль» в full_menu и student_menu
- `database/crud.py` — get_user() включает role и is_blocked
- `tests/test_schedule.py` — исправлены моки TokenManager и тексты ошибок

### v0.3.5 — Фаза 3: Уведомления — APScheduler + /settings + кеширование

**Система уведомлений:**
- APScheduler (AsyncIOScheduler) — ежедневные задачи с CronTrigger
- Оценки — ежедневно в 18:00, ДЗ — ежедневно в 19:00 (настраивается в .env)
- Последовательная рассылка с паузой 2.5 сек (rate limit МЭШ API: 30/мин)
- Обработка ошибок: TelegramForbiddenError → авто-отключение уведомлений
- Очистка старого кеша — еженедельно (воскресенье 03:00)

**Кеширование (определение новых данных):**
- Таблицы `grades_cache`, `homework_cache` с флагом `is_notified`
- Ключ уникальности оценки: (subject, grade_value, date, lesson_type)
- Ключ уникальности ДЗ: (subject, assignment[:100], due_date)
- Защита от дублирования при перезапуске бота

**Команда /settings:**
- Inline-кнопки вкл/выкл для оценок и ДЗ
- Студентам скрыта кнопка оценок (у них нет доступа к оценкам)
- Дефолтные настройки создаются автоматически при первом заходе
- Кнопка «Настройки» добавлена в главное меню всех ролей
- `/settings` добавлена в Telegram Menu (кнопка «Меню»)

**Новые файлы:**
- `services/notification_service.py` — ядро уведомлений (APScheduler + рассылка)
- `handlers/settings.py` — handler /settings с inline-кнопками

**Изменённые файлы:**
- `database/crud.py` — CRUD для grades_cache, homework_cache, рассылки (~150 строк)
- `bot.py` — интеграция APScheduler (init, start, shutdown) + settings router
- `keyboards/main_menu.py` — кнопка «Настройки» в full_menu и student_menu
- `handlers/start.py` — /settings в _set_user_commands для всех ролей

### v0.3.4 — Ролевое меню: единое меню для всех ролей + Telegram Menu по ролям

**Меню по ролям — переработка:**
- Админ и родитель получают полное меню (расписание, оценки, ДЗ, тесты, результаты, перерегистрация)
- Студент получает ограниченное меню (расписание, ДЗ, тесты, результаты — без оценок)
- Кнопка «Меню» в Telegram показывает команды под роль пользователя (BotCommandScopeChat)
- Студенту теперь доступна регистрация МЭШ (для расписания и ДЗ)
- Добавлена команда `/test` (раньше тест запускался только через inline-кнопку)

**Баг-фиксы:**
- Перерегистрация МЭШ больше не теряет роль пользователя (сохранение и восстановление роли)
- `create_user()` теперь обрабатывает уже существующие записи (UPDATE вместо ошибки INSERT)
- После регистрации МЭШ показывается inline-меню вместо текстового списка команд

**Изменённые файлы:**
- `keyboards/main_menu.py` — `parent_menu_keyboard()` + `admin_menu_keyboard()` → `full_menu_keyboard()`, обновлён `student_menu_keyboard()`
- `handlers/start.py` — `_set_user_commands()`, обновлены `cmd_start`, `go_home`, `cb_reregister`
- `handlers/language.py` — добавлен обработчик `/test`
- `handlers/registration.py` — inline-меню после регистрации вместо текста
- `database/crud.py` — `create_user()` теперь UPSERT
- `bot.py` — минимальные default-команды (персональные устанавливаются в /start)

### v0.3.3 — Оценки (/ocenki) и Домашние задания (/dz) — завершение Фазы 2

**Оценки (`/ocenki`):**
- Команда `/ocenki` и кнопка «Оценки» из меню
- Фильтрация по периодам: Сегодня / Неделя / Месяц
- Группировка по дате (новые сверху), отображение предмета, оценки, типа контроля и комментария
- Выбор ребёнка при нескольких детях
- IDOR-защита, HTML-экранирование, обработка ошибок с кнопкой «Повторить»
- Проверка `profile_id` — предложение перерегистрации при отсутствии

**Домашние задания (`/dz`):**
- Команда `/dz` и кнопка «Домашние задания» из меню
- Фильтрация по периодам: Сегодня / Завтра / Неделя (смотрят вперёд)
- Группировка по дате (ближайшие сверху), отображение предмета и текста задания
- Обрезка длинных заданий (500 символов) и общей длины сообщения (3800 символов)
- Выбор ребёнка, IDOR-защита, HTML-экранирование, обработка ошибок

**Новые файлы:**
- `handlers/ocenki.py` — обработчик оценок
- `handlers/dz.py` — обработчик домашних заданий

**Изменённые файлы:**
- `handlers/start.py` — удалена заглушка `cb_not_implemented` для Оценки/ДЗ
- `bot.py` — зарегистрированы новые роутеры `ocenki.router` и `dz.router`
- `CLAUDE.md` — обновлена структура проекта и навигация

### v0.3.2 — Навигация: кнопка «Главное меню» во всех разделах бота

**Навигация:**
- Новая общая функция `home_button()` в `keyboards/main_menu.py` — единый источник кнопки возврата
- Кнопка «🏠 Главное меню» добавлена в расписание (под кнопками Сегодня/Завтра/Неделя, Повторить, выбор ребёнка)
- Кнопка «🏠 Главное меню» добавлена в ответы админ-команд (`/allow`, `/block`, `/users`)
- Заглушки для нереализованных пунктов меню (Оценки, ДЗ) — сообщение «в разработке» + кнопка возврата
- Кнопка возврата в сообщениях об ошибках (вместо текста «нажмите /start»)
- Рефакторинг: все клавиатуры используют `home_button()` вместо хардкода

**Изменённые файлы:**
- `keyboards/main_menu.py` — функция `home_button()`, рефакторинг `quiz_home_keyboard()`
- `keyboards/quiz_kb.py` — использует `home_button()` в `language_keyboard()`
- `handlers/schedule.py` — кнопка в 3 клавиатурах + ошибках
- `handlers/admin.py` — кнопка в ответах на команды
- `handlers/start.py` — заглушка `cb_not_implemented` для Оценки/ДЗ

### v0.3.1 — Исправление запуска бота: создание админа, кнопки меню, автовосстановление

**Баг-фиксы:**
- **Создание админа на свежей БД**: `_ensure_admin()` падал молча из-за NOT NULL на `mesh_login`/`mesh_password` — INSERT теперь включает пустые значения, NOT NULL убран из `init.sql`
- **Кнопка "Расписание" не работала**: в меню админа/родителя кнопка отправляла `callback_data="menu:raspisanie"`, но обработчика не было — добавлен `cb_menu_raspisanie` в `schedule.py`
- **Автовосстановление админа**: если главный админ удалил себя через "Перерегистрировать МЭШ" и нажал `/start`, бот показывал "Доступ ограничен" — теперь `/start` автоматически восстанавливает запись ADMIN_ID
- **Логирование ошибок**: молчаливый `except: pass` в `_ensure_admin` заменён на `logging.warning`

**Изменённые файлы:**
- `core/database.py` — фикс INSERT + логирование
- `database/migrations/init.sql` — mesh_login/mesh_password теперь nullable
- `handlers/schedule.py` — обработчик кнопки "Расписание" из меню
- `handlers/start.py` — автовосстановление админа в `/start`

### v0.3.0 — Слияние school_bot + school_helper: единый бот для родителей и учеников

**Ролевая система:**
- Три роли: admin, parent, student — определяются при добавлении через `/allow`
- Главный админ (ADMIN_ID) создаётся автоматически при запуске, неудаляем
- Access Control Middleware — проверка роли на каждый запрос
- Публичные команды (/start, /help) доступны всем; остальные — по роли

**Меню по ролям:**
- `/start` определяет роль и показывает соответствующее меню
- Родитель без МЭШ-токена → запуск регистрации (логин/пароль/SMS)
- Родитель с МЭШ-токеном → меню МЭШ (расписание, оценки, ДЗ)
- Ученик → меню тестирования (начать тест, история, прогресс)
- Админ → полное меню + команды управления

**Тестирование по языкам (из school_helper):**
- Генерация тестов через LLM (LM Studio / Qwen2.5-7B на localhost:1234)
- 4 типа вопросов: выбор ответа, верно/неверно, заполнить пропуск, перевод
- Дедупликация вопросов (не повторяет недавние)
- Языки: English (intermediate), Spanish (beginner)
- Настраиваемые темы и количество вопросов (5/10/15/20)
- История тестов, статистика, слабые темы

**Админ-команды:**
- `/allow <user_id> [student|parent|admin]` — добавить пользователя
- `/block <user_id>` — заблокировать
- `/users` — список всех пользователей с ролями

**Новые файлы:**
- `middlewares/access.py` — Access Control Middleware
- `keyboards/main_menu.py` — клавиатуры по ролям
- `keyboards/quiz_kb.py` — клавиатуры квизов
- `llm/client.py`, `llm/prompts.py`, `llm/parser.py` — LLM-интеграция
- `services/test_generator.py`, `services/answer_checker.py`, `services/progress_tracker.py`
- `handlers/quiz.py`, `handlers/language.py`, `handlers/topic.py`, `handlers/quiz_settings.py`, `handlers/history.py`, `handlers/admin.py`
- `states/quiz_states.py` — FSM-состояния квиза
- `database/migrations/003_add_quiz_and_access.sql` — роли, таблицы тестов

**Инфраструктура:**
- Прокси для Telegram Bot API через AiohttpSession + aiohttp-socks
- Миграция БД: колонки role, is_blocked, last_active + таблицы test_sessions, question_results
- ~15 новых CRUD-функций в database/crud.py
- SSH-ключ в `.env` через `~` (тильда) — работает на любом ПК
- Автопоиск Git SSH в `bot.py` — Kata-17 (`E:/Progs/Git`), Lenovo (`D:/Programs/Git`), стандартная установка

### v0.2.3 — Исправление авторизации без SMS + файловое логирование
- **OAuth callback fix**: при входе без SMS (прямой редирект на school.mos.ru), `_auth_complete` теперь сигнализируется сразу при получении OAuth callback — убрано зависание на 30 секунд
- **mes_role fix**: маппинг `ParentProfile` → `parent` в заголовке `x-mes-role` для API get_events (расписание не загружалось)
- **Файловое логирование**: RotatingFileHandler → `data/logs/bot.log` (5MB, 3 бэкапа, UTF-8) — ранее логи шли только в stdout
- **Задержка перед cookie extraction**: 2с ожидание после OAuth callback перед извлечением токена из cookies браузера
- **Улучшенное логирование ошибок API**: детальный вывод raw error в client.py при ошибках get_schedule

### v0.2.2 — Human-like авторизация: защита от обнаружения автоматизации
- **Проблема**: mos.ru обнаружил автоматизированный вход и сбросил пароль аккаунта
- **Человеческий ввод**: `fill()` заменён на посимвольный `type()` с задержкой 50–150мс
- **Случайные паузы**: фиксированный `sleep(1.5)` заменён на случайные 1.5–3.0с
- **Движения мыши**: `_random_mouse_move()` перед кликами и вводом текста
- **Скролл страницы**: небольшой скролл перед вводом логина (имитация чтения)
- **Рандомизация viewport**: 1280×800 → ±20px (борьба с фингерпринтингом)
- **Обнаружение блокировки**: "подозрительная активность" распознаётся и выдаёт инструкцию по восстановлению
- **Кулдаун авторизации**: 60с между попытками (предотвращает "долбёжку" сервера)

### v0.2.1 — Stealth-браузер: patchright + обход антибот-защиты mos.ru
- Новый модуль `mesh_api/browser_factory.py` — запуск "невидимого" Chromium
  - Приоритет: patchright (обход CDP-детекции) → fallback на стандартный playwright
  - playwright-stealth + ручные JS-скрипты (только для стандартного playwright, не для patchright)
  - `--disable-async-dns` — решена проблема DNS (Chromium использовал мёртвый VPN-DNS вместо системного)
- Переработан `playwright_auth.py` — новый flow school.mos.ru:
  - school.mos.ru теперь React SPA с кнопкой "МЭШID" (больше нет авторедиректа на login.mos.ru)
  - `_click_meshid_button()` — клик по кнопке МЭШID
  - `_wait_for_login_page()` — поллинг URL вместо wait_for_url (не ждёт load event)
  - login.mos.ru: логин и пароль на одной странице (поддержка и старого, и нового flow)
  - `wait_until="networkidle"` вместо `"commit"` для React SPA
- `HybridMeshAuth` в `auth.py` — автооткат Playwright → curl_cffi при неудаче
- Настройки в `config.py`: `MESH_AUTH_HEADLESS`, `MESH_AUTH_STEALTH`
- Зависимости: +patchright, +playwright-stealth

### v0.2.0 — curl_cffi: обход JA3 TLS-фингерпринтинга login.mos.ru
- Диагностика подтвердила: TCP OK, TLS от Python/OpenSSL заблокирован по JA3 фингерпринту
- Установлен curl_cffi 0.14.0 (BoringSSL + Chrome TLS impersonation)
- OctoDiary async_.py: добавлен _CurlSession wrapper; ClientSession заменён на curl_cffi для MES login
- OctoDiary enter_sms_code.py: FormData → plain dict (совместимо с curl_cffi)
- /testauth: добавлен Тест 5 — curl_cffi GET к login.mos.ru для подтверждения Chrome TLS

### v0.1.9 — TLS-диагностика и увеличение таймаутов
- Добавлен Тест 4 в /testauth: изолированный TLS-handshake через asyncio.open_connection(ssl=True)
- Исправлены утечки сессий в /testauth: finally-блок закрывает внутреннюю aiohttp-сессию OctoDiary
- OctoDiary: connect timeout 15с → 30с, total 30с → 120с (TLS login.mos.ru ~15-20с)
- auth.py: _AUTH_TIMEOUT 20с → 90с (flow = несколько запросов, каждый может ждать TLS)

### v0.1.8 — Диагностика таймаутов МЭШ
- Увеличен connect timeout OctoDiary: 5с → 15с, total: 15с → 30с (патч installed package)
- Переписан /testauth: правильный порядок except (aiohttp.ConnectionTimeoutError перед asyncio.TimeoutError)
- Добавлен Тест 3 в /testauth: чистый TCP-коннект к login.mos.ru:443 через asyncio.open_connection
- Расшифровка результатов в конце вывода /testauth

### v0.1.7 — Исправление авторизации МЭШ
- Заменена зависимость octodiary==0.3.0 (PyPI) → форк Mag329/OctoDiary-py с исправленными заголовками (Accept: */*)
- Добавлен таймаут 20с на авторизацию (asyncio.wait_for) вместо 31с TCP-таймаута
- Исправлена утечка aiohttp-сессий после таймаута: явное закрытие и сброс api-объекта
- Диагностика: JWT рабочий, проблема — сервер МЭШ сбрасывает соединения при накоплении незакрытых сессий

### v0.1.6 — Переход на OctoDiary (авторизация через mos.ru)
- Полная переработка авторизации: старый API dnevnik.mos.ru мёртв, теперь через OctoDiary + mos.ru OAuth2
- SMS-верификация при регистрации (новый шаг в FSM)
- Обновление токена через refresh_token (без повторного SMS)
- Новые поля в БД: mesh_refresh_token, mesh_client_id, mesh_client_secret, mesh_profile_id, person_id
- Миграция 002 для обновления существующих БД
- Расписание через events API (person_id + mes_role)
- Добавлена зависимость: octodiary==0.3.0

### v0.1.5 — Команда /raspisanie
- Реализована команда /raspisanie — расписание уроков из МЭШ
- Token Manager — автообновление токена МЭШ с asyncio.Lock
- Inline-кнопки: Сегодня / Завтра / Неделя
- Выбор ребёнка при нескольких детях
- IDOR-защита и HTML-экранирование данных API
- Обработка ошибок с кнопкой «Повторить»
- 30 unit-тестов (pytest + pytest-asyncio)

### v0.1.4 — Меню команд бота
- Меню команд бота в Telegram (set_my_commands)

### v0.1.3 — Ограничение доступа
- Белый список пользователей, роли, команды /allow /block /users

### v0.1.0 — Начальная версия
- Создана структура проекта
- Реализована аутентификация через МЭШ
- Регистрация пользователей (FSM)
- Шифрование паролей (Fernet)
- База данных SQLite
- Команда /start
