# School Bot — Единый школьный Telegram-бот (v1.7.4)

Telegram-бот для родителей и учеников, объединяющий два сервиса:
- **Для родителей**: расписание, оценки, домашние задания через МЭШ (Московская электронная школа)
- **Для учеников**: тестирование по школьным предметам (English, Spanish) через AI с геймификацией

Доступ управляется администратором. Бот определяет роль пользователя и показывает соответствующее меню.

Фикс устойчивости МЭШ-сессии: fallback-токены без `refresh_token` больше не принудительно
считаются истёкшими через локальные 24 часа, поэтому бот не должен сам провоцировать
ежедневный повторный SMS-вход.

## Возможности

### Для родителей (role=parent) — полный доступ
- ✅ **Аутентификация через МЭШ** — вход через mos.ru с шифрованием паролей (patchright stealth + curl_cffi)
- ✅ **Расписание уроков** — на сегодня, завтра или всю неделю (`/raspisanie`)
- ✅ **Оценки** — за сегодня, неделю или месяц (`/ocenki`)
- ✅ **Аналитика оценок** — средний балл по предметам, тренды, распределение, сравнение периодов
- ✅ **Домашние задания** — на сегодня, завтра или неделю (`/dz`)
- ✅ **Тестирование по языкам** — English, Spanish через AI
- 👨‍👩‍👧‍👦 **Несколько детей** — поддержка до 5 детей на одного родителя

### Для учеников (role=student) — расписание, ДЗ, тесты, соревнования
- ✅ **Расписание уроков** — на сегодня, завтра или всю неделю (`/raspisanie`)
- ✅ **Домашние задания** — на сегодня, завтра или неделю (`/dz`)
- ✅ **Тестирование по языкам** — English, Spanish, French, German с адаптивной сложностью (CEFR A1-C1)
- ✅ **Тесты по школьным предметам** — математика, история, биология
- ✅ **AI-генерация тестов** — через LLM bridge (HTTPS) или локальный LM Studio
- ✅ **Адаптивная сложность** — авто-определение уровня из класса ученика, ручной выбор для родителей
- ✅ **6 типов вопросов** — выбор ответа, верно/неверно, заполнить пропуск, перевод, сопоставление, аудио
- ✅ **Голосовые ответы** — распознавание через Whisper/STT
- ✅ **История и статистика** — прогресс, слабые темы, результаты
- ✅ **Геймификация** — XP, уровни, серии, 11 значков, ежедневные задания
- ✅ **5 тем оформления** — Нейтральный, Minecraft, Ninjago, Космос, Супергерой
- ✅ **Соревнования и социальные функции** — лидерборд XP, недельный челлендж, обмен результатами

### Для администратора (role=admin)
- ✅ **Управление пользователями** — `/allow`, `/block`, `/users`
- ✅ **Ролевая система** — admin, parent, student
- ✅ **Главный админ** (ADMIN_ID) — неудаляемый, создаётся автоматически

### Общее
- 🔐 **Безопасность** — пароли зашифрованы (Fernet), Access Control Middleware
- 🔔 **Уведомления** — ежедневные оповещения: оценки в 18:00, ДЗ в 19:00, досылка пропущенных при рестарте (`/settings`)
- ⏰ **Планировщик напоминаний** — вечернее напоминание о контрольных и ДЗ на завтра
- 📝 **Личные напоминания** — ежедневные пользовательские напоминания через `/remind`
- ⚙️ **Настройки** — вкл/выкл уведомлений через inline-кнопки (`/settings`)
- 👤 **Профиль** — просмотр профиля, роли и привязанных детей (`/profile`)
- 📡 **Статус МЭШ API в профиле** — live-проверка доступности + fallback-индикатор кеша
- ♻️ **Retry-очередь уведомлений** — автоматические повторные попытки при временных сбоях
- 🚨 **Алерт админу** — сигнал при длительной недоступности МЭШ API
- 🛡️ **Rate limiting** — защита от спама пользователей + лимит запросов к МЭШ API
- 🌐 **Прокси** — поддержка SOCKS5 для Telegram API и МЭШ + SSH-туннель

## Технологии

- **Python 3.9+**
- **aiogram 3.25** — асинхронная Telegram Bot библиотека
- **aiosqlite** — асинхронная работа с SQLite
- **pydantic-settings** — конфигурация через .env
- **cryptography (Fernet)** — шифрование паролей
- **patchright / playwright** — stealth-браузер для авторизации mos.ru
- **openai** — клиент для LM Studio (OpenAI-совместимый API)
- **OctoDiary** — неофициальный клиент МЭШ API

## Установка

### 1. Клонирование и настройка

```bash
git clone <your-repo-url>
cd school-bot
python -m venv venv

# Windows
venv\Scripts\activate
# Linux/Mac
source venv/bin/activate

pip install -r requirements.txt

# Скачать браузер Chromium для авторизации МЭШ
patchright install chromium
```

### 2. Настройка окружения

Скопируйте `.env.example` в `.env` и заполните:

```env
# Telegram Bot (от @BotFather)
BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz

# Ключ шифрования (сгенерировать: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
ENCRYPTION_KEY=ваш_ключ

# Главный администратор (Telegram ID)
ADMIN_ID=123456789

# Admin web panel (v1.6.0)
ADMIN_WEB_ENABLED=true
# Use 127.0.0.1 for secure access via SSH tunnel.
# Use 0.0.0.0 only if you intentionally expose the panel outside.
ADMIN_WEB_HOST=127.0.0.1
ADMIN_WEB_PORT=8088
ADMIN_WEB_TOKEN=change_me_strong_secret

# Прокси (опционально, для обхода блокировок)
# MESH_PROXY_URL=socks5://127.0.0.1:1080

# LLM для тестов (bridge -> direct fallback)
# LLM_BRIDGE_URL=https://your-bridge-domain/v1
# LLM_API_KEY=your_strong_bridge_token
# LLM_BASE_URL=http://localhost:1234/v1
# LLM_MODEL=qwen2.5-7b-instruct
# LLM_REQUEST_TIMEOUT=120
# LLM_FALLBACK_ENABLED=true
```

### 3. Запуск

```bash
python bot.py
```

## Использование

### Для администратора

1. Запустите бота, отправьте `/start`
2. Добавьте пользователей:
   - `/allow 123456789 parent` — добавить родителя
   - `/allow 987654321 student` — добавить ученика
   - `/allow 111222333 admin` — добавить админа
3. `/block 123456789` — заблокировать пользователя
4. `/users` — список всех пользователей

### Для родителя

1. Админ добавляет вас: `/allow <ваш_id> parent`
2. Вы отправляете `/start` → бот запускает МЭШ-регистрацию (логин → пароль → SMS)
3. После регистрации доступны: расписание, оценки, ДЗ

### Для ученика

1. Админ добавляет вас: `/allow <ваш_id> student`
2. Вы отправляете `/start` → бот запускает МЭШ-регистрацию (логин → пароль → SMS)
3. После регистрации доступны: расписание, ДЗ, тесты
4. Выбираете язык → тему → количество вопросов → проходите тест
5. Смотрите историю и статистику

### Команды

| Команда | Описание |
|---------|----------|
| `/start` | Главное меню (по роли) |
| `/raspisanie` | Расписание уроков |
| `/ocenki` | Оценки (админ, родитель) |
| `/dz` | Домашние задания |
| `/test` | Пройти тест по языку |
| `/social` | Соревнования и соц-функции (ученик) |
| `/share <token>` | Открыть shared-результат |
| `/social_admin` | Соц-отчёт по ученикам (админ) |
| `/import_questions` | Импорт вопросов из JSON (админ/родитель) |
| `/allow <id> [role]` | Добавить пользователя (админ) |
| `/block <id>` | Заблокировать (админ) |
| `/users` | Список пользователей (админ) |
| `/health` | Health check бота (админ) |
| `/settings` | Настройки уведомлений |
| `/remind` | Личные ежедневные напоминания |
| `/profile` | Мой профиль |
| `/report` | PDF-отчеты (расписание/оценки) |
| `/help` | Справка |

Примечание по `/health`: если `bridge` доступен, недоступный `direct` (`localhost:1234`) показывается как ожидаемый резервный путь, а не как критическая ошибка.

## Структура проекта

```
.
├── bot.py                     # Точка входа
├── config.py                  # Настройки (pydantic-settings)
├── requirements.txt           # Зависимости
├── .env                       # Переменные окружения (не в git!)
│
├── core/                      # Основная логика
│   ├── database.py            # Инициализация БД, миграции
│   └── encryption.py          # Шифрование (Fernet)
│
├── mesh_api/                  # МЭШ API
│   ├── auth.py                # Аутентификация (HybridMeshAuth)
│   ├── client.py              # API клиент
│   ├── playwright_auth.py     # Browser-авторизация
│   ├── browser_factory.py     # Stealth-браузер
│   ├── proxy_patch.py         # SOCKS5 патч для OctoDiary
│   ├── endpoints.py           # URL endpoints
│   ├── models.py              # Модели данных
│   └── exceptions.py          # Исключения
│
├── handlers/                  # Telegram handlers
│   ├── start.py               # /start (меню по ролям)
│   ├── registration.py        # МЭШ-регистрация (FSM)
│   ├── schedule.py            # /raspisanie
│   ├── ocenki.py              # /ocenki
│   ├── dz.py                  # /dz
│   ├── admin.py               # /allow, /block, /users
│   ├── quiz.py                # Прохождение теста
│   ├── language.py            # Выбор языка
│   ├── topic.py               # Выбор темы
│   ├── quiz_settings.py       # Настройки теста
│   ├── history.py             # История тестов
│   ├── analytics.py            # Аналитика оценок
│   ├── settings.py            # /settings (уведомления)
│   ├── reminders.py           # /remind (личные напоминания)
│   ├── profile.py             # /profile (мой профиль)
│   ├── import_questions.py    # /import_questions (импорт банка вопросов)
│   └── social.py              # /social, /share (соревнования и соц-функции)
│
├── keyboards/                 # Telegram клавиатуры
│   ├── main_menu.py           # Меню по ролям
│   └── quiz_kb.py             # Клавиатуры квизов
│
├── middlewares/                # Middleware
│   ├── access.py              # Access Control (проверка ролей)
│   └── throttle.py            # Anti-spam (flood control)
│
├── llm/                       # LLM-интеграция (bridge/direct)
│   ├── client.py              # OpenAI-совместимый клиент
│   ├── prompts.py             # Промпты для генерации тестов
│   └── parser.py              # Парсинг JSON-ответов LLM
│
├── llm_bridge/                # Локальный Bearer-proxy для LM Studio
│   ├── server.py              # Bridge сервис (/health, /v1/*)
│   └── README.md              # Как запускать bridge на ПК с LLM
│
├── services/                  # Бизнес-логика
│   ├── test_generator.py      # Генерация тестов
│   ├── fallback_test_generator.py # Шаблонный fallback-генератор
│   ├── answer_checker.py      # Проверка ответов
│   ├── progress_tracker.py    # Статистика и прогресс
│   ├── notification_service.py # Уведомления (APScheduler)
│   ├── gamification.py        # Геймификация (XP, уровни, серии, значки, темы)
│   ├── level_adapter.py       # Адаптивная сложность (CEFR, авто-определение уровня)
│   └── analytics.py           # Аналитика оценок (средние, тренды, распределение)
│
├── states/                    # FSM states
│   ├── registration.py        # Регистрация МЭШ
│   └── quiz_states.py         # Квиз
│
├── database/                  # База данных
│   ├── crud.py                # CRUD операции
│   └── migrations/            # SQL миграции
│       ├── init.sql
│       ├── 002_octodiary.sql
│       ├── 003_add_quiz_and_access.sql
│       ├── 005_gamification.sql
│       ├── 006_adaptive_difficulty.sql
│       ├── 007_reminders.sql
│       ├── 008_quiz_expansion.sql
│       └── 009_social_features.sql
│
├── utils/                     # Утилиты
│   ├── token_manager.py       # Обновление токена МЭШ
│   └── rate_limiter.py        # Rate limiter для МЭШ API
│
└── data/                      # Runtime data
    ├── school_bot.db          # SQLite БД
    └── logs/                  # Логи
```

## Безопасность

- Пароли МЭШ зашифрованы (Fernet symmetric encryption)
- Сообщения с паролями автоматически удаляются
- Access Control Middleware проверяет роль на каждый запрос
- Parameterized SQL queries (защита от SQL injection)
- Ключ шифрования и токены — только в `.env` (не в git)

## Разработка

### Текущий прогресс

- ✅ Фаза 1: Фундамент
- ✅ Фаза 2: Основные команды (расписание, оценки, ДЗ, навигация)
- ✅ Фаза 3: Уведомления (APScheduler, /settings, кеширование)
- ✅ Фаза 4: Production (rate limiting, /help, /profile, устойчивые уведомления, 72 теста)
- ✅ Фаза 5: Геймификация (XP, уровни, серии, значки, 5 тем, ежедневные задания, 118 тестов)
- ✅ Фаза 6: Адаптивная сложность (CEFR-уровни, авто-определение, темы по уровням, 145 тестов)
- ✅ Фаза 7: Аналитика оценок (средний балл, тренды, распределение, сравнение периодов, 193 теста)
- ✅ Фаза 8: Устойчивость уведомлений (v0.9.0-v1.1.0: retry, fallback, алерты)
- ✅ Фаза 9: Напоминания и планировщик (v1.2.0: контрольные, ДЗ на завтра, `/remind`)

### Завершено в v1.5.0

- Соревнования и социальные функции
- Таблица лидеров по XP среди учеников
- Еженедельные челленджи
- Достижения за регулярность
- Обмен результатами между учениками
- Расширение квизов
- Новые языки (французский, немецкий)
- Квизы по школьным предметам (математика, история, биология)
- Новые типы вопросов (сопоставление, аудио)
- Импорт вопросов из файла (учитель может загрузить)
- Голосовые ответы в квизах (Whisper/STT)

### v1.5.1

- Добавлена админ-команда `/social_admin` для сводки по соревнованиям:
  лидерборд XP, недельный челлендж, регулярность учеников.

### v1.5.2

- Исправлен `/help`: HTML-экранирование `/share &lt;token&gt;`.
- Добавлены/закреплены тесты для social-admin и help-рендеринга.

### v1.5.3

- Добавлен версионируемый deploy-скрипт `work/deploy-school-bot.ps1`.
- Устранены ложные падения деплоя (состояние `activating`, CRLF в remote-script, несовместимость `systemctl status`).

### v1.6.0

- Веб-панель админа: встроенный web-интерфейс `/admin` (статистика + график тестов).
- Групповые рассылки от админа из веб-панели с выбором ролей и dry-run.
- Логирование рассылок в БД (`admin_broadcasts`, `admin_broadcast_recipients`).

### v1.7.0

- Добавлен `/report`: экспорт PDF-документов по расписанию (today/tomorrow/week).
- Для admin/parent в `/report` добавлен экспорт PDF по оценкам (today/week/month).
- В админ-панели добавлена история запусков групповых рассылок (последние 30 запусков).

#### Admin Web access (VPS)

- Correct URL always includes token and `/admin` path:
  - `http://127.0.0.1:8088/admin?token=<ADMIN_WEB_TOKEN>`
  - `http://<server-ip>:8088/admin?token=<ADMIN_WEB_TOKEN>`
- If `ADMIN_WEB_HOST=127.0.0.1`, open panel through SSH tunnel (recommended):

```powershell
$key="$env:USERPROFILE\.ssh\id_ed25519_rag"
ssh -L 8088:127.0.0.1:8088 -i $key -p 4422 school_bot@45.152.113.91
```

- Then open in browser:
  - `http://127.0.0.1:8088/admin?token=<ADMIN_WEB_TOKEN>`
- If you open by external IP without tunnel, `ADMIN_WEB_HOST` must be `0.0.0.0` and firewall must allow port `8088`.

### Ближайший план: v1.8.0

- Экспорт и фильтрация отчетов в админ-панели (CSV/PDF).

### Известные проблемы

1. МЭШ API неофициальное — endpoints могут измениться
2. Для LLM-моста нужен защищённый endpoint (`LLM_BRIDGE_URL`) и токен (`LLM_API_KEY`)
3. Если bridge и direct endpoint недоступны, бот использует шаблонный fallback-тест
3. mos.ru может обнаружить автоматизацию (v0.2.2 снижает риск)
4. Для прод-использования LLM-моста нужен внешний защищённый канал до локального bridge (например, Cloudflare Tunnel/Tailscale/WireGuard)

### Диагностика fallback в тестах

- Бот явно показывает режим генерации: `Режим: LLM` или `Режим: fallback`.
- При `fallback` бот также выводит короткую причину (например: `direct endpoint failed: Connection error`).
- На VPS нельзя использовать только `LLM_BASE_URL=http://localhost:1234/v1`, если LM Studio запущен на другом ПК.
- Для прода задайте в серверном `.env`:
  - `LLM_BRIDGE_URL=https://<ваш-bridge>/v1`
  - `LLM_API_KEY=<токен bridge>`
  - `LLM_BASE_URL` можно оставить как резервный fallback.

### Быстрая проверка LLM стека (v1.7.1)

- Новый скрипт: `work/check-llm-stack.ps1`
- Что проверяет:
  - локальный LM Studio (`127.0.0.1:1234/v1/models`)
  - локальный bridge (`127.0.0.1:8787/v1/models`, с Bearer токеном)
  - серверный reverse-tunnel endpoint (`127.0.0.1:12340/v1/models`)
  - ключевые LLM-переменные в `/opt/school_bot/.env`

Пример запуска:

```powershell
powershell -ExecutionPolicy Bypass -File .\work\check-llm-stack.ps1 -BridgeToken "<TOKEN>"
```

Перед проверкой обычно нужно поднять reverse tunnel:

```powershell
powershell -ExecutionPolicy Bypass -File .\work\start-llm-reverse-tunnel.ps1
```

## Лицензия

MIT License

## Авторы

Разработано с помощью Claude Code

---
HISTORY UPDATE (2026-03-09)
Current stable version: v1.7.2

v1.7.1
- Fixed fallback diagnostics and mode visibility.
- Fixed fallback question pools:
  - English pool expanded to prevent repeats in 10-question sessions.
  - Mathematics/History/Biology pools separated to prevent subject mixing.
- Improved subject-specific prompt isolation for school subjects.
- Added LLM stack diagnostics and one-click launch tools:
  - work/check-llm-stack.ps1
  - work/start-llm-stack.ps1
  - work/Start-LlmStack.bat
- Fixed launcher script issues:
  - PowerShell Host variable conflict removed.
  - Invoke-WebRequest script parsing prompt suppressed.
  - Environment variable assignment handling fixed.

v1.7.2
- Fixed deploy script to preserve server environment files:
  - Excludes .env and .env.* during sync.
- Confirmed production bridge+tunnel runtime path on server:
  - LLM_BRIDGE_URL=http://127.0.0.1:12340/v1
  - LLM API key configured on server.
- Verified tunnel endpoint health from VPS side (HTTP 200).

Quick admin web access (secure)
- Keep ADMIN_WEB_HOST=127.0.0.1 on server.
- Open SSH tunnel:
  ssh -L 8088:127.0.0.1:8088 -i ~/.ssh/id_ed25519_rag -p 4422 school_bot@45.152.113.91
- Open in browser:
  http://127.0.0.1:8088/admin?token=<ADMIN_WEB_TOKEN>

---
HISTORY UPDATE (2026-03-09, Katana17)
Current stable version: v1.7.4

v1.7.4
- Fixed forced daily МЭШ reauth for fallback sessions without OAuth refresh data.
- Fallback tokens are no longer treated as expired by a local 24h timer.
- The bot now keeps such sessions until the API returns a real 401.
- Added regression tests for token manager behavior with and without OAuth refresh data.

v1.7.3
- Homework notifications now include explicit due date in each item.
- Default /dz period changed to next school day (+1 school day).
- 5-day school week rule added:
  - Friday -> Monday
  - Saturday -> Monday
- Student homework push logic updated:
  - send only after last lesson end time + 30 minutes
  - periodic checks every 10 minutes
  - fallback to HOMEWORK_NOTIFICATION_TIME when no lessons are present
- Deployed to VPS and verified service status: active.

Katana17 execution notes
- Local repo/workdir: E:\claude\school_bot
- Local shell: Windows PowerShell
- SSH/SCP binaries used by deploy script:
  - E:\Progs\Git\usr\bin\ssh.exe
  - E:\Progs\Git\usr\bin\scp.exe
- SSH key used:
  - C:\Users\Олег\.ssh\id_ed25519_rag
- Production deploy command used:
  - work/deploy-school-bot.ps1 -SourceDir e:/claude/school_bot

Git fixation
- Commit: d334ec6
- Tag: v1.7.4
- Pushed: origin/main and origin/v1.7.4

Notification fixes (2026-03-10)
- Homework notifications: one summary per student for the next school day, sent 30 minutes after that student's last lesson.
- Homework notifications no longer split into separate partial messages during the day and are not resent for the same student/date.
- Grade notifications now always include the student name and the report date in the message header.

Homework updates extension (2026-03-10)
- Added a separate delayed-updates pipeline for homework with polling every 15 minutes.
- After the first daily summary is sent, the bot checks MES for newly added or changed homework and sends delta notifications.
- Delta notifications explicitly separate "Added" and "Changed" items per student and are delivered to all homework subscribers (parent/student accounts).
- Fixed lesson-window check call to MES schedule API (`person_id` + `mes_role`) to match client signature.
