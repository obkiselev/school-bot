-- Migration 005: Gamification (XP, streaks, achievements, daily challenges)

CREATE TABLE IF NOT EXISTS user_stats (
    user_id INTEGER PRIMARY KEY,
    xp_total INTEGER DEFAULT 0,
    xp_today INTEGER DEFAULT 0,
    xp_today_date TEXT,
    current_streak INTEGER DEFAULT 0,
    longest_streak INTEGER DEFAULT 0,
    last_quiz_date TEXT,
    level INTEGER DEFAULT 1,
    theme TEXT DEFAULT 'neutral',
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS achievements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    badge_key TEXT NOT NULL,
    earned_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, badge_key),
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS daily_challenges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    challenge_date TEXT NOT NULL,
    subject TEXT NOT NULL,
    topic TEXT NOT NULL,
    is_completed INTEGER DEFAULT 0,
    xp_reward INTEGER DEFAULT 50,
    UNIQUE(user_id, challenge_date),
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);
