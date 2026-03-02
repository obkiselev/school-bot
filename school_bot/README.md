# Школьный помощник - Telegram-бот для МЭШ (v0.2.3)

Telegram-бот для родителей школьников, интегрированный с системой «Московская электронная школа» (МЭШ). Автоматизация получения информации о школьной жизни: расписание уроков, оценки и домашние задания.

## Возможности

- ✅ **Аутентификация через МЭШ** - безопасный вход с шифрованием паролей (patchright stealth + curl_cffi fallback)
- ✅ **Расписание уроков** - на сегодня, завтра или всю неделю (команда /raspisanie)
- ⏳ **Оценки** - с возможностью фильтрации по датам и предметам (в разработке)
- ⏳ **Домашние задания** - актуальная информация о заданиях (в разработке)
- 🔔 **Автоматические уведомления** - ежедневные оповещения об оценках и ДЗ
- 👨‍👩‍👧‍👦 **Несколько детей** - поддержка до 5 детей на одного родителя
- 🔐 **Безопасность** - все пароли хранятся в зашифрованном виде (Fernet)

## Технологии

- **Python 3.9+**
- **aiogram 3.25** - асинхронная Telegram Bot библиотека
- **aiohttp** - для работы с МЭШ API
- **SQLite** - база данных
- **cryptography (Fernet)** - шифрование паролей
- **patchright** - stealth-браузер для обхода антибот-защиты mos.ru
- **APScheduler** - планировщик уведомлений (в разработке)

## Установка

### 1. Клонирование репозитория

```bash
git clone <your-repo-url>
cd school_bot
```

### 2. Создание виртуального окружения

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Linux/Mac
source venv/bin/activate
```

### 3. Установка зависимостей

```bash
pip install -r requirements.txt
```

### 4. Настройка окружения

Скопируйте `.env.example` в `.env`:

```bash
cp .env.example .env
```

Заполните `.env` файл:

```env
# Получите токен от @BotFather в Telegram
BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz

# Сгенерируйте ключ шифрования:
# python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
ENCRYPTION_KEY=ваш_сгенерированный_ключ_здесь
```

### 5. Генерация ключа шифрования

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Скопируйте результат в `.env` как `ENCRYPTION_KEY`.

### 6. Запуск бота

```bash
cd school_bot
python bot.py
```

Вы должны увидеть:

```
✅ Database initialized successfully at data/school_bot.db
Starting bot polling...
```

## Использование

### Первый запуск

1. Найдите бота в Telegram (по имени, которое вы указали в @BotFather)
2. Отправьте `/start`
3. Введите логин от МЭШ (dnevnik.mos.ru)
4. Введите пароль (сообщение автоматически удалится)
5. Выберите детей из списка
6. Подтвердите выбор

### Команды

| Команда | Описание |
|---------|----------|
| `/start` | Начало работы, регистрация |
| `/raspisanie` | Расписание уроков |
| `/ocenki` | Оценки |
| `/dz` | Домашние задания |
| `/profile` | Мой профиль (в разработке) |
| `/settings` | Настройки уведомлений (в разработке) |
| `/help` | Справка (в разработке) |

### Уведомления

По умолчанию включены:
- **18:00** - уведомления об оценках за день
- **19:00** - уведомления о домашних заданиях на завтра

> ⚠️ Функция уведомлений будет реализована в Фазе 3

## Структура проекта

```
school_bot/
├── bot.py                     # Точка входа
├── config.py                  # Настройки (pydantic-settings)
├── requirements.txt           # Зависимости
├── .env                       # Переменные окружения (не в git!)
├── .env.example               # Пример .env
├── README.md                  # Документация
│
├── core/                      # Основная логика
│   ├── database.py            # Работа с БД
│   ├── encryption.py          # Шифрование
│   ├── scheduler.py           # APScheduler (в разработке)
│   └── middlewares.py         # Middlewares (в разработке)
│
├── mesh_api/                  # МЭШ API
│   ├── client.py              # Основной клиент
│   ├── auth.py                # Аутентификация (HybridMeshAuth: Playwright → curl_cffi)
│   ├── playwright_auth.py     # Browser-авторизация через Chromium
│   ├── browser_factory.py     # Stealth-запуск браузера (patchright/playwright)
│   ├── endpoints.py           # URL endpoints
│   ├── models.py              # Модели данных
│   └── exceptions.py          # Исключения
│
├── handlers/                  # Telegram handlers
│   ├── start.py               # /start
│   ├── registration.py        # Регистрация (FSM)
│   ├── schedule.py            # /raspisanie
│   ├── grades.py              # /ocenki (в разработке)
│   ├── homework.py            # /dz (в разработке)
│   ├── settings.py            # /settings (в разработке)
│   └── profile.py             # /profile (в разработке)
│
├── keyboards/                 # Telegram клавиатуры (в разработке)
├── states/                    # FSM states
│   └── registration.py        # States для регистрации
│
├── database/                  # База данных
│   ├── models.py              # SQL схемы (в разработке)
│   ├── crud.py                # CRUD операции
│   └── migrations/
│       └── init.sql           # Начальная схема
│
└── data/                      # Runtime data
    ├── school_bot.db          # SQLite БД
    └── logs/                  # Логи (в разработке)
```

## Безопасность

### Шифрование

Все пароли МЭШ хранятся в зашифрованном виде с использованием **Fernet (symmetric encryption)**:

- ✅ Пароли никогда не логируются
- ✅ Сообщения с паролями автоматически удаляются
- ✅ Ключ шифрования хранится в `.env` (не в git!)
- ✅ Использование parameterized queries для защиты от SQL injection

### Рекомендации

1. **Никогда не коммитьте `.env` файл**
2. Регулярно меняйте `ENCRYPTION_KEY` (требуется пересохранение всех паролей)
3. Используйте отдельный токен бота для production
4. Не предоставляйте доступ к БД файлу посторонним

## Разработка

### Фаза 1: Фундамент ✅ (Завершена)

- ✅ Структура проекта
- ✅ База данных (SQLite)
- ✅ Шифрование (Fernet)
- ✅ МЭШ API client
- ✅ Регистрация пользователей (FSM)
- ✅ Базовый bot.py

### Фаза 2: Основные команды (В разработке)

- ✅ `/raspisanie` - расписание уроков (v0.1.5)
- ✅ Stealth-браузер авторизации: patchright + playwright-stealth (v0.2.1)
- ✅ Автооткат Playwright → curl_cffi при неудаче (v0.2.1)
- ✅ Human-like авторизация: посимвольный ввод, случайные паузы, движения мыши (v0.2.2)
- ✅ Исправление авторизации без SMS + файловое логирование (v0.2.3)
- ⏳ `/ocenki` - оценки
- ⏳ `/dz` - домашние задания
- ⏳ Клавиатуры навигации
- ⏳ Middleware для аутентификации

### Фаза 3: Уведомления (Планируется)

- ⏳ APScheduler setup
- ⏳ Ежедневные уведомления (18:00 - оценки, 19:00 - ДЗ)
- ⏳ `/settings` - настройка уведомлений
- ⏳ Кеширование для определения новых оценок

### Фаза 4: Production (Планируется)

- ✅ Логирование (RotatingFileHandler) (v0.2.3)
- ⏳ Rate limiting
- ⏳ `/help` и `/profile`
- ⏳ Unit tests
- ⏳ Деплой на VPS

## Известные проблемы

1. **МЭШ API не официальное** - endpoints могут измениться без предупреждения
2. **Fallback на scraping** - если API перестанет работать, потребуется BeautifulSoup
3. **Ограничения rate limit** - не более 30 запросов в минуту

## Troubleshooting

### "Database initialized successfully" but bot not responding

- Проверьте `BOT_TOKEN` в `.env`
- Убедитесь, что токен активен в @BotFather

### "ENCRYPTION_KEY not found"

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Скопируйте в `.env`

### "МЭШ API недоступна"

- Проверьте интернет-соединение
- Попробуйте позже (возможны технические работы на стороне МЭШ)

## Лицензия

MIT License - см. LICENSE файл

## Авторы

Разработано с помощью Claude Code

## Контакты

- Issues: [GitHub Issues](https://github.com/your-repo/issues)
- Email: your-email@example.com
