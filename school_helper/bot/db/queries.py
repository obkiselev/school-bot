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
