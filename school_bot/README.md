# School Bot — Единый школьный Telegram-бот (v0.3.4)

Telegram-бот для родителей и учеников, объединяющий два сервиса:
- **Для родителей**: расписание, оценки, домашние задания через МЭШ (Московская электронная школа)
- **Для учеников**: тестирование по школьным предметам (English, Spanish) через AI

Доступ управляется администратором. Бот определяет роль пользователя и показывает соответствующее меню.

## Возможности

### Для родителей (role=parent) — полный доступ
- ✅ **Аутентификация через МЭШ** — вход через mos.ru с шифрованием паролей (patchright stealth + curl_cffi)
- ✅ **Расписание уроков** — на сегодня, завтра или всю неделю (`/raspisanie`)
- ✅ **Оценки** — за сегодня, неделю или месяц (`/ocenki`)
- ✅ **Домашние задания** — на сегодня, завтра или неделю (`/dz`)
- ✅ **Тестирование по языкам** — English, Spanish через AI
- 👨‍👩‍👧‍👦 **Несколько детей** — поддержка до 5 детей на одного родителя

### Для учеников (role=student) — расписание, ДЗ, тесты
- ✅ **Расписание уроков** — на сегодня, завтра или всю неделю (`/raspisanie`)
- ✅ **Домашние задания** — на сегодня, завтра или неделю (`/dz`)
- ✅ **Тестирование по языкам** — English (intermediate), Spanish (beginner)
- ✅ **AI-генерация тестов** — через LM Studio (Qwen2.5-7B) локально
- ✅ **4 типа вопросов** — выбор ответа, верно/неверно, заполнить пропуск, перевод
- ✅ **История и статистика** — прогресс, слабые темы, результаты

### Для администратора (role=admin)
- ✅ **Управление пользователями** — `/allow`, `/block`, `/users`
- ✅ **Ролевая система** — admin, parent, student
- ✅ **Главный админ** (ADMIN_ID) — неудаляемый, создаётся автоматически

### Общее
- 🔐 **Безопасность** — пароли зашифрованы (Fernet), Access Control Middleware
- 🔔 **Уведомления** — ежедневные оповещения об оценках и ДЗ (в разработке)
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
cd school_bot
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

# Прокси (опционально, для обхода блокировок)
# MESH_PROXY_URL=socks5://127.0.0.1:1080

# LLM для тестов (LM Studio на localhost)
# LLM_BASE_URL=http://localhost:1234/v1
# LLM_MODEL=qwen2.5-7b-instruct
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
| `/allow <id> [role]` | Добавить пользователя (админ) |
| `/block <id>` | Заблокировать (админ) |
| `/users` | Список пользователей (админ) |
| `/help` | Справка |

## Структура проекта

```
school_bot/
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
│   └── history.py             # История тестов
│
├── keyboards/                 # Telegram клавиатуры
│   ├── main_menu.py           # Меню по ролям
│   └── quiz_kb.py             # Клавиатуры квизов
│
├── middlewares/                # Middleware
│   └── access.py              # Access Control (проверка ролей)
│
├── llm/                       # LLM-интеграция (LM Studio)
│   ├── client.py              # OpenAI-совместимый клиент
│   ├── prompts.py             # Промпты для генерации тестов
│   └── parser.py              # Парсинг JSON-ответов LLM
│
├── services/                  # Бизнес-логика
│   ├── test_generator.py      # Генерация тестов
│   ├── answer_checker.py      # Проверка ответов
│   └── progress_tracker.py    # Статистика и прогресс
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
│       └── 003_add_quiz_and_access.sql
│
├── utils/                     # Утилиты
│   └── token_manager.py       # Обновление токена МЭШ
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
- ⏳ Фаза 3: Уведомления
- ⏳ Фаза 4: Production

### Известные проблемы

1. МЭШ API неофициальное — endpoints могут измениться
2. LM Studio должен быть запущен локально для работы тестов
3. mos.ru может обнаружить автоматизацию (v0.2.2 снижает риск)

## Лицензия

MIT License

## Авторы

Разработано с помощью Claude Code
