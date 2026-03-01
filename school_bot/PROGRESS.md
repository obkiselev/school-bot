# School Bot — Прогресс разработки

## Текущая версия: 0.2.1

## Статус: Фаза 2 в работе — авторизация через mos.ru (OctoDiary)

---

## Общая картина проекта

Сейчас существуют два отдельных проекта:

- **school_bot** (этот проект) — помощник для родителей: расписание, оценки, домашние задания, уведомления. Интеграция с МЭШ.
- **school_helper** (отдельный проект) — помощник для учеников: прохождение тестов по школьным предметам.

**Конечная цель**: объединить оба сервиса в один — **school_bot** — единый школьный сервис и для родителей, и для детей-учеников.

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

## Фаза 2: Основные команды — В РАБОТЕ

- [x] /raspisanie — расписание уроков (сегодня/завтра/неделя)
- [x] Автоматическое обновление токена МЭШ (utils/token_manager.py)
- [x] Inline-кнопки переключения периода
- [x] Выбор ребёнка при нескольких детях
- [x] IDOR-защита (проверка владельца student_id)
- [x] HTML-экранирование данных МЭШ API
- [x] Обработка ошибок МЭШ API с кнопкой «Повторить»
- [x] Unit-тесты для расписания (30 тестов, 100% pass)
- [ ] /ocenki — оценки с фильтрацией по датам и предметам
- [ ] /dz — домашние задания
- [ ] Клавиатуры навигации
- [ ] Middleware для проверки аутентификации

## Фаза 3: Уведомления — В ПЛАНАХ

- [ ] APScheduler setup
- [ ] Ежедневные уведомления (18:00 — оценки, 19:00 — ДЗ)
- [ ] /settings — настройка уведомлений
- [ ] Кеширование для определения новых оценок

## Фаза 4: Production — В ПЛАНАХ

- [ ] Логирование (RotatingFileHandler)
- [ ] Rate limiting
- [ ] /help и /profile
- [ ] Деплой на VPS

---

## Известные баги и проблемы

- МЭШ API через OctoDiary — при обновлении библиотеки могут сломаться типы данных
- Нет middleware для проверки авторизации перед командами
- Тесты нужно обновить под новое API (старые моки не работают)

---

## Changelog

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
