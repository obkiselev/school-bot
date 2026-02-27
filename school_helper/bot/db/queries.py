from bot.db.database import get_db


async def ensure_user(user_id: int, username: str | None = None, first_name: str | None = None):
    """Create or update a user record."""
    db = await get_db()
    await db.execute(
        """INSERT INTO users (user_id, username, first_name)
           VALUES (?, ?, ?)
           ON CONFLICT(user_id) DO UPDATE SET
               username = excluded.username,
               first_name = excluded.first_name,
               last_active = datetime('now')""",
        (user_id, username, first_name),
    )
    await db.commit()


async def save_test_session(
    user_id: int,
    language: str,
    topic: str,
    total: int,
    correct: int,
    percent: float,
    answers: list[dict],
) -> int:
    """Save a completed test session and its individual question results."""
    db = await get_db()

    cursor = await db.execute(
        """INSERT INTO test_sessions (user_id, language, topic, total_questions, correct_answers, score_percent)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (user_id, language, topic, total, correct, percent),
    )
    session_id = cursor.lastrowid

    for a in answers:
        await db.execute(
            """INSERT INTO question_results
               (session_id, question_type, question_text, correct_answer, user_answer, is_correct, explanation)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                session_id,
                a.get("question_type", ""),
                a.get("question_text", ""),
                a.get("correct_answer", ""),
                a.get("user_answer", ""),
                1 if a.get("is_correct") else 0,
                a.get("explanation", ""),
            ),
        )

    await db.commit()
    return session_id


async def get_user_sessions(user_id: int, limit: int = 10) -> list[dict]:
    """Get recent test sessions for a user."""
    db = await get_db()
    cursor = await db.execute(
        """SELECT id, language, topic, total_questions, correct_answers, score_percent, finished_at
           FROM test_sessions
           WHERE user_id = ?
           ORDER BY finished_at DESC
           LIMIT ?""",
        (user_id, limit),
    )
    rows = await cursor.fetchall()
    return [dict(row) for row in rows]


async def get_weak_topics(user_id: int) -> list[dict]:
    """Get topics where the user scored below 70%, sorted by weakest first."""
    db = await get_db()
    cursor = await db.execute(
        """SELECT language, topic, AVG(score_percent) as avg_score, COUNT(*) as attempts
           FROM test_sessions
           WHERE user_id = ?
           GROUP BY language, topic
           HAVING avg_score < 70
           ORDER BY avg_score ASC""",
        (user_id,),
    )
    rows = await cursor.fetchall()
    return [dict(row) for row in rows]


async def get_recent_questions(
    user_id: int, language: str, topic: str, limit: int = 50
) -> list[str]:
    """Get recent question texts for a user+language+topic to avoid duplicates."""
    db = await get_db()
    cursor = await db.execute(
        """SELECT qr.question_text
           FROM question_results qr
           JOIN test_sessions ts ON qr.session_id = ts.id
           WHERE ts.user_id = ?
             AND ts.language = ?
             AND ts.topic = ?
           ORDER BY ts.finished_at DESC, qr.id DESC
           LIMIT ?""",
        (user_id, language, topic, limit),
    )
    rows = await cursor.fetchall()
    return [row["question_text"] for row in rows]


async def get_stats_summary(user_id: int) -> dict:
    """Get overall stats for a user."""
    db = await get_db()
    cursor = await db.execute(
        """SELECT
               COUNT(*) as total_tests,
               AVG(score_percent) as avg_score,
               SUM(total_questions) as total_questions_answered,
               SUM(correct_answers) as total_correct
           FROM test_sessions
           WHERE user_id = ?""",
        (user_id,),
    )
    row = await cursor.fetchone()
    return dict(row) if row else {}


async def is_user_allowed(user_id: int) -> tuple[bool, str | None]:
    """Check if user is in whitelist and not blocked. Returns (is_allowed, role)."""
    db = await get_db()
    cursor = await db.execute(
        "SELECT role, is_blocked FROM users WHERE user_id = ?",
        (user_id,),
    )
    row = await cursor.fetchone()
    if row is None:
        return (False, None)
    if row["is_blocked"]:
        return (False, row["role"])
    return (True, row["role"])


async def set_user_access(user_id: int, role: str = "student") -> None:
    """Add or update a user with given role. Also unblocks if was blocked."""
    db = await get_db()
    await db.execute(
        """INSERT INTO users (user_id, role, is_blocked)
           VALUES (?, ?, 0)
           ON CONFLICT(user_id) DO UPDATE SET
               role = excluded.role,
               is_blocked = 0""",
        (user_id, role),
    )
    await db.commit()


async def block_user(user_id: int) -> bool:
    """Block a user. Returns True if user existed, False otherwise."""
    db = await get_db()
    cursor = await db.execute(
        "UPDATE users SET is_blocked = 1 WHERE user_id = ?",
        (user_id,),
    )
    await db.commit()
    return cursor.rowcount > 0


async def get_all_users_list() -> list[dict]:
    """Get all users with their roles and block status."""
    db = await get_db()
    cursor = await db.execute(
        "SELECT user_id, first_name, username, role, is_blocked FROM users ORDER BY user_id",
    )
    rows = await cursor.fetchall()
    return [dict(row) for row in rows]
