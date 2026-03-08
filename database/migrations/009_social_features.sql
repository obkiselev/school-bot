-- Migration 009: Competitions and social features (v1.5.0)

CREATE TABLE IF NOT EXISTS shared_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    share_token TEXT NOT NULL UNIQUE,
    from_user_id INTEGER NOT NULL,
    session_id INTEGER NOT NULL,
    created_at TEXT DEFAULT (datetime('now')),
    expires_at TEXT,
    FOREIGN KEY (from_user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (session_id) REFERENCES test_sessions(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_shared_results_token ON shared_results(share_token);
CREATE INDEX IF NOT EXISTS idx_shared_results_user ON shared_results(from_user_id, created_at DESC);
