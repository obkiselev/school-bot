School Bot — Единый школьный Telegram-бот
Текущая версия: 1.7.4

Последний фикс МЭШ-сессии:
- fallback-токены без OAuth refresh-данных больше не протухают по локальному таймеру 24h;
  бот использует их до реального 401 от МЭШ API и не должен сам вызывать ежедневный SMS-вход.

============================================
ПЛАН РАЗВИТИЯ
============================================

--- Завершено ---

v0.1.x — Фундамент: структура, авторизация МЭШ, регистрация, шифрование, БД
v0.2.x — TLS-обход, stealth-браузер, human-like авторизация, логирование
v0.3.x — Расписание, оценки, ДЗ, ролевая система, навигация, слияние с school_helper
v0.4.x — Rate limiting, /help, /profile, устойчивые уведомления, 72 теста
v0.5.0 — Геймификация: XP, уровни, серии, значки, 5 тем оформления (118 тестов)
v0.6.0 — Адаптивная сложность: CEFR-уровни, авто-определение для учеников (145 тестов)
v0.6.1 — Деплой на VPS, отключение SSH-туннеля
v0.7.0 — Аналитика оценок: средний балл, тренды, распределение (193 теста)
v0.8.0 — Стабилизация: устранение тихих ошибок и улучшение диагностического логирования
v0.9.0 — Устойчивость к сбоям (этап 1): надёжная обработка уведомлений и итоговая статистика отправки
v1.0.0 — Устойчивость к сбоям (этап 2): статус МЭШ API в /profile + fallback на кеш
v1.1.0 — Устойчивость к сбоям (этап 3): retry-очередь + алерт админу при длительной недоступности API
v1.2.0 — Напоминания и планировщик: вечерние напоминания о контрольных/ДЗ на завтра + личные /remind
v1.2.1 — LLM-мост: bridge -> direct -> fallback для генерации тестов
v1.2.2 — Явная индикация режима генерации тестов (LLM/fallback) + причина fallback
v1.3.0 — Стабильный релиз (этап): /health для админа + CI workflow (автотесты)
v1.4.0 — Стабилизация LLM-моста: корректный health для схемы bridge+tunnel, диагностика fallback и эксплуатационные фиксы
v1.5.0 — Соревнования и социальные функции
  - Таблица лидеров по XP среди учеников
  - Еженедельные челленджи (кто больше тестов пройдёт)
  - Достижения за регулярность (30 дней подряд и т.д.)
  - Обмен результатами между учениками
v1.5.0 — Расширение квизов
  - Новые языки (французский, немецкий)
  - Квизы по школьным предметам (математика, история, биология)
  - Новые типы вопросов (сопоставление, аудио)
  - Импорт вопросов из файла (учитель может загрузить)
  - Голосовые ответы в квизах (Whisper/STT)
v1.5.1 — Админ-сводка соревнований
  - Команда /social_admin для просмотра лидерборда, недельного челленджа и регулярности
v1.5.2 — Стабилизация help и релиз соц-админки
  - Исправлен /help (корректный HTML для /share &lt;token&gt;)
  - Закреплены изменения social-admin и тесты
v1.5.3 — Стабилизация деплоя
  - Добавлен версионируемый deploy-скрипт в work/
  - Устранены ложные падения deploy (activating/CRLF/systemctl status)
v1.6.0 — Веб-панель и рассылки
  - Веб-панель админа (статистика пользователей, графики)
  - Групповые рассылки от админа
  - Экспорт оценок/расписания в PDF (планируется)
v1.7.0 — Документы и отчеты
  - Экспорт оценок/расписания в PDF (/report)
  - История массовых рассылок в веб-панели

--- Планируется ---
v1.8.0 — Отчеты панели
  - Экспорт истории рассылок в CSV/PDF
  - Фильтры и поиск в истории рассылок

============================================
БЫСТРЫЙ СТАРТ
============================================

1. Установить зависимости:
   cd school-bot
   pip install -r requirements.txt

2. Создать .env файл:
   cp .env.example .env

3. Настроить .env:
   BOT_TOKEN=ваш_токен_от_BotFather
   ENCRYPTION_KEY=сгенерированный_ключ
   (сгенерировать: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")

4. Запустить бота:
   python bot.py

5. Протестировать:
   - Найти бота в Telegram
   - /start
   - Ввести логин/пароль mos.ru
   - Ввести SMS-код
   - Выбрать детей

ADMIN WEB QUICK ACCESS (v1.6.0)
- URL must be: /admin?token=<ADMIN_WEB_TOKEN>
- Secure way (recommended): keep ADMIN_WEB_HOST=127.0.0.1 and use SSH tunnel.
  ssh -L 8088:127.0.0.1:8088 -i ~/.ssh/id_ed25519_rag -p 4422 school_bot@45.152.113.91
- Then open: http://127.0.0.1:8088/admin?token=<ADMIN_WEB_TOKEN>
- Direct external access requires ADMIN_WEB_HOST=0.0.0.0 and open firewall port 8088.

v1.7.0 STATUS (done)
- Added command /report for PDF export:
  - schedule: today/tomorrow/week
  - grades (admin/parent): today/week/month
- Added broadcast history block to admin web panel (last 30 runs).

v1.7.1 STATUS (in progress)
- Fixed fallback quiz pools:
  - English pool expanded to avoid repeating first 5 questions when 10 are requested.
  - Mathematics/History/Biology now use separate fallback pools (no cross-subject mixing).
- Prompt isolation for school subjects:
  - Mathematics/History/Biology now have dedicated prompt examples and explicit anti-mixing rule.
- Added quick health script:
  - `work/check-llm-stack.ps1`

LLM QUICK CHECK (v1.7.1)
1) Start LM Studio local server (`127.0.0.1:1234`).
2) Start local bridge (`127.0.0.1:8787`) with token.
3) Start reverse tunnel to VPS:
   `powershell -ExecutionPolicy Bypass -File .\work\start-llm-reverse-tunnel.ps1`
4) Run full check:
   `powershell -ExecutionPolicy Bypass -File .\work\check-llm-stack.ps1 -BridgeToken "<TOKEN>"`

Expected result:
- `[OK] LM Studio local`
- `[OK] Bridge local`
- `[OK] Server checks`

If failed, script prints exact failing layer (local LM Studio, local bridge, or VPS tunnel/env).

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

---
HISTORY SYNC (2026-03-09)
- Synced: readme.txt <-> _repo/readme.txt
- Stable version reference: v1.7.4

NOTIFICATION FIXES (2026-03-10)
- Homework notifications now send one summary per student for the next school day, exactly after last lesson end + 30 minutes.
- Homework summaries no longer arrive in separate fragments and are suppressed after the first successful send for the same student/date.
- Grade notifications now always show the student name and the report date.

HOMEWORK UPDATES EXTENSION (2026-03-10)
- Added separate periodic check for delayed MES homework updates: every 15 minutes.
- After the first summary for the day, bot tracks newly added or changed homework and sends a delta notification.
- Delta notification explicitly separates Added vs Changed items per student and is sent to homework subscribers (parent/student accounts).
- Fixed schedule API call in lesson-window check: now uses `person_id` and `mes_role` (no invalid `profile_id` argument).
