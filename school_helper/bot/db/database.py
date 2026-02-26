import os
import aiosqlite

from bot.config import DB_PATH

_db: aiosqlite.Connection | None = None


async def get_db() -> aiosqlite.Connection:
    """Get or create the database connection."""
    global _db
    if _db is None:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        _db = await aiosqlite.connect(DB_PATH)
        _db.row_factory = aiosqlite.Row
        await _create_tables(_db)
    return _db


async def close_db():
    """Close the database connection."""
    global _db
    if _db:
        await _db.close()
        _db = None


async def _create_tables(db: aiosqlite.Connection):
    await db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            user_id       INTEGER PRIMARY KEY,
            username      TEXT,
            first_name    TEXT,
            created_at    TEXT DEFAULT (datetime('now')),
            last_active   TEXT DEFAULT (datetime('now'))
        );

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
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        );

        CREATE TABLE IF NOT EXISTS question_results (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id      INTEGER NOT NULL,
            question_type   TEXT NOT NULL,
            question_text   TEXT NOT NULL,
            correct_answer  TEXT NOT NULL,
            user_answer     TEXT,
            is_correct      INTEGER NOT NULL,
            explanation     TEXT,
            FOREIGN KEY (session_id) REFERENCES test_sessions(id)
        );
    """)
    await db.commit()
