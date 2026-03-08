-- v1.6.0: admin web panel + broadcast logs

CREATE TABLE IF NOT EXISTS admin_broadcasts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    initiated_by INTEGER,
    message_text TEXT NOT NULL,
    target_roles TEXT NOT NULL,
    total_targets INTEGER DEFAULT 0,
    sent_count INTEGER DEFAULT 0,
    failed_count INTEGER DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'running', -- running|completed|failed|dry_run
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    finished_at DATETIME,
    FOREIGN KEY (initiated_by) REFERENCES users(user_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS admin_broadcast_recipients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    broadcast_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    status TEXT NOT NULL, -- queued|sent|failed
    error_text TEXT,
    delivered_at DATETIME,
    FOREIGN KEY (broadcast_id) REFERENCES admin_broadcasts(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_admin_broadcasts_created_at
    ON admin_broadcasts(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_admin_broadcast_recipients_broadcast
    ON admin_broadcast_recipients(broadcast_id, status);
