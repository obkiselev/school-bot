-- Migration 008: Quiz expansion (languages/subjects + import from file)

CREATE TABLE IF NOT EXISTS imported_questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    language TEXT NOT NULL,
    level TEXT NOT NULL,
    topic TEXT NOT NULL,
    question_json TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_imported_questions_lookup
ON imported_questions(language, level, topic, created_at DESC);
