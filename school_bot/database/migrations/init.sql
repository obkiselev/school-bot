-- database/migrations/init.sql
-- Initial database schema for МЭШ School Bot

-- Users table (Telegram users / parents)
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,                    -- Telegram user ID
    username TEXT,                                   -- Telegram username
    first_name TEXT,
    last_name TEXT,
    registered_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    mesh_login TEXT NOT NULL,                       -- МЭШ login (encrypted)
    mesh_password TEXT NOT NULL,                    -- МЭШ password (encrypted)
    mesh_token TEXT,                                -- Session token (encrypted)
    token_expires_at DATETIME,
    last_sync DATETIME,
    is_active BOOLEAN DEFAULT 1,
    mesh_refresh_token TEXT,                        -- OAuth refresh_token (encrypted)
    mesh_client_id TEXT,                             -- OAuth client_id (encrypted)
    mesh_client_secret TEXT,                         -- OAuth client_secret (encrypted)
    mesh_profile_id INTEGER,                         -- profile_id из МЭШ API
    mesh_role TEXT                                    -- Роль: parent/student
);

-- Children table (student profiles)
CREATE TABLE IF NOT EXISTS children (
    child_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,                       -- Reference to parent
    student_id INTEGER NOT NULL,                    -- МЭШ student ID
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    middle_name TEXT,
    class_name TEXT,                                -- e.g., "9А"
    school_name TEXT,
    is_active BOOLEAN DEFAULT 1,
    added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    person_id TEXT,                                  -- contingent_guid для events API
    class_unit_id INTEGER,                           -- class_unit_id из МЭШ
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

-- Notification settings
CREATE TABLE IF NOT EXISTS notification_settings (
    setting_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    child_id INTEGER,                               -- NULL = applies to all children
    notification_type TEXT NOT NULL,                -- 'grades', 'homework', 'schedule'
    is_enabled BOOLEAN DEFAULT 1,
    notification_time TEXT,                         -- HH:MM format
    timezone TEXT DEFAULT 'Europe/Moscow',
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (child_id) REFERENCES children(child_id) ON DELETE CASCADE,
    UNIQUE(user_id, child_id, notification_type)
);

-- Grades cache (to detect new grades)
CREATE TABLE IF NOT EXISTS grades_cache (
    grade_id INTEGER PRIMARY KEY AUTOINCREMENT,
    child_id INTEGER NOT NULL,
    subject TEXT NOT NULL,
    grade_value TEXT NOT NULL,                      -- e.g., "5", "4-", "зачет"
    date DATE NOT NULL,
    lesson_type TEXT,                               -- "контрольная", "домашняя работа"
    teacher TEXT,
    comment TEXT,
    is_notified BOOLEAN DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (child_id) REFERENCES children(child_id) ON DELETE CASCADE
);

-- Homework cache (to avoid duplicate notifications)
CREATE TABLE IF NOT EXISTS homework_cache (
    homework_id INTEGER PRIMARY KEY AUTOINCREMENT,
    child_id INTEGER NOT NULL,
    subject TEXT NOT NULL,
    assignment TEXT NOT NULL,
    due_date DATE NOT NULL,
    is_notified BOOLEAN DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (child_id) REFERENCES children(child_id) ON DELETE CASCADE
);

-- Activity log (for debugging and analytics)
CREATE TABLE IF NOT EXISTS activity_log (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    action TEXT NOT NULL,                           -- 'login', 'command', 'notification_sent'
    details TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE SET NULL
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_children_user ON children(user_id);
CREATE INDEX IF NOT EXISTS idx_grades_child ON grades_cache(child_id, date);
CREATE INDEX IF NOT EXISTS idx_homework_child ON homework_cache(child_id, due_date);
CREATE INDEX IF NOT EXISTS idx_notifications_user ON notification_settings(user_id);
CREATE INDEX IF NOT EXISTS idx_activity_timestamp ON activity_log(timestamp);
