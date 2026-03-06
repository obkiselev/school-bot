-- Миграция 003: Добавление поддержки тестирования по языкам и контроля доступа
-- Дата: 2026-03-02

-- Поля контроля доступа в существующую таблицу users
ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'parent';
ALTER TABLE users ADD COLUMN is_blocked INTEGER DEFAULT 0;
ALTER TABLE users ADD COLUMN last_active TEXT;

-- Существующие пользователи (у кого есть mesh_login) — родители
UPDATE users SET role = 'parent' WHERE mesh_login IS NOT NULL AND role IS NULL;

-- Таблица тестовых сессий
CREATE TABLE IF NOT EXISTS test_sessions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL,
    language        TEXT NOT NULL,
    topic           TEXT NOT NULL,
    total_questions INTEGER NOT NULL,
    correct_answers INTEGER NOT NULL,
    score_percent   REAL NOT NULL,
    started_at      TEXT DEFAULT (datetime('now')),
    finished_at     TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

-- Таблица результатов по вопросам
CREATE TABLE IF NOT EXISTS question_results (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      INTEGER NOT NULL,
    question_type   TEXT NOT NULL,
    question_text   TEXT NOT NULL,
    correct_answer  TEXT NOT NULL,
    user_answer     TEXT,
    is_correct      INTEGER NOT NULL,
    explanation     TEXT,
    FOREIGN KEY (session_id) REFERENCES test_sessions(id) ON DELETE CASCADE
);

-- Индексы
CREATE INDEX IF NOT EXISTS idx_test_sessions_user ON test_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_question_results_session ON question_results(session_id);
