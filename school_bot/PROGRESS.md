# School Bot — Прогресс разработки

## Текущая версия: 0.3.6

## Статус: Фаза 4 частично — rate limiting, /help, /profile

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
- [x] Unit-тесты для расписания (30 тестов, 100% pass)
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

## Фаза 4: Production — В РАБОТЕ

- [x] Логирование (RotatingFileHandler) — реализовано в v0.2.3
- [x] Rate limiting — глобальный token-bucket для МЭШ API + per-user throttle middleware
- [x] /help — справка по командам (по роли)
- [x] /profile — профиль пользователя (маскировка логина, дети, роль)
- [x] Баг-фикс: get_user() теперь возвращает role и is_blocked
- [x] Баг-фикс: исправлены тесты TokenManager (MeshClient → MeshAuth)
- [ ] Деплой на VPS

---

## Известные баги и проблемы

- МЭШ API через OctoDiary — при обновлении библиотеки могут сломаться типы данных
- mos.ru может обнаружить автоматизацию и сбросить пароль (v0.2.2 снижает риск)
- LLM (LM Studio) должен быть запущен локально для работы квизов
- **curl_cffi TLS таймаут через SSH-туннель**: TCP pre-check прокси проходит (OK), но TLS-соединение с mos.ru зависает 15с и отваливается. Возможные причины: SSH-сервер блокирует HTTPS к mos.ru, mos.ru блокирует IP сервера, или MTU/фрагментация мешает TLS-handshake. Пока обходим через Playwright fallback.
- **Playwright: после установки patchright нужно скачать браузер** — выполнить `patchright install chromium` (иначе ошибка "Executable doesn't exist")

---

## Changelog

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
