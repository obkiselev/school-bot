-- Migration 007: custom reminders table for /remind command

CREATE TABLE IF NOT EXISTS custom_reminders (
    reminder_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    reminder_text TEXT NOT NULL,
    reminder_time TEXT NOT NULL,
    is_enabled BOOLEAN DEFAULT 1,
    last_sent_date DATE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_custom_reminders_user ON custom_reminders(user_id, is_enabled);
