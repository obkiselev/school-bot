"""CRUD operations for database."""
from typing import Optional, List, Dict
from datetime import datetime

from core.database import get_db
from core.encryption import encrypt, decrypt


# ============================================================================
# USER OPERATIONS
# ============================================================================

async def create_user(
    user_id: int,
    username: Optional[str],
    first_name: Optional[str],
    last_name: Optional[str],
    mesh_login: str,
    mesh_password: str,
    mesh_token: Optional[str] = None,
    token_expires_at: Optional[str] = None,
    mesh_refresh_token: Optional[str] = None,
    mesh_client_id: Optional[str] = None,
    mesh_client_secret: Optional[str] = None,
    mesh_profile_id: Optional[int] = None,
    mesh_role: Optional[str] = None,
) -> bool:
    """
    Create or update user with encrypted credentials.

    If user already exists (e.g. from /allow or reregister),
    updates MES data while preserving role and is_blocked.
    """
    db = get_db()

    encrypted_login = encrypt(mesh_login)
    encrypted_password = encrypt(mesh_password)
    encrypted_token = encrypt(mesh_token) if mesh_token else None
    encrypted_refresh = encrypt(mesh_refresh_token) if mesh_refresh_token else None
    encrypted_client_id = encrypt(mesh_client_id) if mesh_client_id else None
    encrypted_client_secret = encrypt(mesh_client_secret) if mesh_client_secret else None

    existing = await db.fetchone("SELECT 1 FROM users WHERE user_id = ?", (user_id,))

    if existing:
        query = """
            UPDATE users SET
                username = ?, first_name = ?, last_name = ?,
                mesh_login = ?, mesh_password = ?, mesh_token = ?, token_expires_at = ?,
                mesh_refresh_token = ?, mesh_client_id = ?, mesh_client_secret = ?,
                mesh_profile_id = ?, mesh_role = ?
            WHERE user_id = ?
        """
        await db.execute(query, (
            username, first_name, last_name,
            encrypted_login, encrypted_password, encrypted_token, token_expires_at,
            encrypted_refresh, encrypted_client_id, encrypted_client_secret,
            mesh_profile_id, mesh_role,
            user_id,
        ))
    else:
        query = """
            INSERT INTO users (
                user_id, username, first_name, last_name,
                mesh_login, mesh_password, mesh_token, token_expires_at,
                mesh_refresh_token, mesh_client_id, mesh_client_secret,
                mesh_profile_id, mesh_role
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        await db.execute(query, (
            user_id, username, first_name, last_name,
            encrypted_login, encrypted_password, encrypted_token, token_expires_at,
            encrypted_refresh, encrypted_client_id, encrypted_client_secret,
            mesh_profile_id, mesh_role,
        ))

    return True


async def get_user(user_id: int) -> Optional[Dict]:
    """
    Get user by Telegram ID with decrypted credentials.

    Args:
        user_id: Telegram user ID

    Returns:
        User dict with decrypted credentials or None
    """
    db = get_db()

    query = """
        SELECT user_id, username, first_name, last_name, registered_at,
               mesh_login, mesh_password, mesh_token, token_expires_at,
               last_sync, is_active,
               mesh_refresh_token, mesh_client_id, mesh_client_secret,
               mesh_profile_id, mesh_role
        FROM users WHERE user_id = ?
    """
    row = await db.fetchone(query, (user_id,))

    if not row:
        return None

    # Decrypt credentials
    return {
        "user_id": row[0],
        "username": row[1],
        "first_name": row[2],
        "last_name": row[3],
        "registered_at": row[4],
        "mesh_login": decrypt(row[5]),
        "mesh_password": decrypt(row[6]),
        "mesh_token": decrypt(row[7]) if row[7] else None,
        "token_expires_at": row[8],
        "last_sync": row[9],
        "is_active": row[10],
        "mesh_refresh_token": decrypt(row[11]) if row[11] else None,
        "mesh_client_id": decrypt(row[12]) if row[12] else None,
        "mesh_client_secret": decrypt(row[13]) if row[13] else None,
        "mesh_profile_id": row[14],
        "mesh_role": row[15],
    }


async def update_user_token(
    user_id: int,
    mesh_token: str,
    token_expires_at: str,
    mesh_refresh_token: Optional[str] = None,
    mesh_client_id: Optional[str] = None,
    mesh_client_secret: Optional[str] = None,
) -> bool:
    """
    Update user's МЭШ session token (and optionally OAuth data).

    Returns:
        True if updated successfully
    """
    db = get_db()

    encrypted_token = encrypt(mesh_token)

    # Собираем поля для обновления
    fields = ["mesh_token = ?", "token_expires_at = ?", "last_sync = CURRENT_TIMESTAMP"]
    params = [encrypted_token, token_expires_at]

    if mesh_refresh_token:
        fields.append("mesh_refresh_token = ?")
        params.append(encrypt(mesh_refresh_token))
    if mesh_client_id:
        fields.append("mesh_client_id = ?")
        params.append(encrypt(mesh_client_id))
    if mesh_client_secret:
        fields.append("mesh_client_secret = ?")
        params.append(encrypt(mesh_client_secret))

    params.append(user_id)
    query = f"UPDATE users SET {', '.join(fields)} WHERE user_id = ?"
    await db.execute(query, tuple(params))

    return True


async def invalidate_token(user_id: int) -> bool:
    """
    Сбрасывает token_expires_at в прошлое, чтобы ensure_token() обновил токен.

    Returns:
        True if updated successfully
    """
    db = get_db()

    query = "UPDATE users SET token_expires_at = '2000-01-01T00:00:00' WHERE user_id = ?"
    await db.execute(query, (user_id,))

    return True


async def user_exists(user_id: int) -> bool:
    """Check if user exists in database."""
    db = get_db()

    query = "SELECT 1 FROM users WHERE user_id = ?"
    result = await db.fetchone(query, (user_id,))

    return result is not None


async def delete_user(user_id: int) -> bool:
    """Delete user and all related data (children, notifications cascade)."""
    db = get_db()
    await db.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
    return True


# ============================================================================
# CHILDREN OPERATIONS
# ============================================================================

async def add_child(
    user_id: int,
    student_id: int,
    first_name: str,
    last_name: str,
    middle_name: Optional[str] = None,
    class_name: Optional[str] = None,
    school_name: Optional[str] = None,
    person_id: Optional[str] = None,
    class_unit_id: Optional[int] = None,
) -> int:
    """
    Add child to user's profile.

    Returns:
        child_id (autoincremented ID)
    """
    db = get_db()

    query = """
        INSERT INTO children (
            user_id, student_id, first_name, last_name,
            middle_name, class_name, school_name, person_id, class_unit_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    conn = await db.connect()
    cursor = await conn.execute(query, (
        user_id, student_id, first_name, last_name,
        middle_name, class_name, school_name, person_id, class_unit_id,
    ))
    await conn.commit()

    return cursor.lastrowid


async def get_user_children(user_id: int) -> List[Dict]:
    """
    Get all children for a user.

    Args:
        user_id: Telegram user ID

    Returns:
        List of child dicts
    """
    db = get_db()

    query = """
        SELECT child_id, user_id, student_id, first_name, last_name,
               middle_name, class_name, school_name, is_active, added_at,
               person_id, class_unit_id
        FROM children
        WHERE user_id = ? AND is_active = 1
        ORDER BY added_at
    """

    rows = await db.fetchall(query, (user_id,))

    children = []
    for row in rows:
        children.append({
            "child_id": row[0],
            "user_id": row[1],
            "student_id": row[2],
            "first_name": row[3],
            "last_name": row[4],
            "middle_name": row[5],
            "class_name": row[6],
            "school_name": row[7],
            "is_active": row[8],
            "added_at": row[9],
            "person_id": row[10],
            "class_unit_id": row[11],
        })

    return children


async def get_child(child_id: int) -> Optional[Dict]:
    """Get child by ID."""
    db = get_db()

    query = """
        SELECT child_id, user_id, student_id, first_name, last_name,
               middle_name, class_name, school_name, is_active, added_at,
               person_id, class_unit_id
        FROM children
        WHERE child_id = ?
    """

    row = await db.fetchone(query, (child_id,))

    if not row:
        return None

    return {
        "child_id": row[0],
        "user_id": row[1],
        "student_id": row[2],
        "first_name": row[3],
        "last_name": row[4],
        "middle_name": row[5],
        "class_name": row[6],
        "school_name": row[7],
        "is_active": row[8],
        "added_at": row[9],
        "person_id": row[10],
        "class_unit_id": row[11],
    }


async def remove_child(child_id: int) -> bool:
    """
    Soft delete a child (set is_active = 0).

    Args:
        child_id: Child's database ID

    Returns:
        True if deleted successfully
    """
    db = get_db()

    query = "UPDATE children SET is_active = 0 WHERE child_id = ?"
    await db.execute(query, (child_id,))

    return True


# ============================================================================
# NOTIFICATION SETTINGS
# ============================================================================

async def create_default_notifications(user_id: int, child_id: Optional[int] = None):
    """
    Create default notification settings for user.

    Args:
        user_id: Telegram user ID
        child_id: Specific child ID or None for all children
    """
    db = get_db()

    notification_types = ["grades", "homework"]
    default_times = {"grades": "18:00", "homework": "19:00"}

    for notif_type in notification_types:
        query = """
            INSERT OR IGNORE INTO notification_settings (
                user_id, child_id, notification_type, is_enabled, notification_time
            ) VALUES (?, ?, ?, 1, ?)
        """
        await db.execute(query, (
            user_id, child_id, notif_type, default_times[notif_type]
        ))


async def get_notification_settings(user_id: int) -> List[Dict]:
    """Get all notification settings for a user."""
    db = get_db()

    query = """
        SELECT setting_id, user_id, child_id, notification_type,
               is_enabled, notification_time, timezone
        FROM notification_settings
        WHERE user_id = ?
    """

    rows = await db.fetchall(query, (user_id,))

    settings = []
    for row in rows:
        settings.append({
            "setting_id": row[0],
            "user_id": row[1],
            "child_id": row[2],
            "notification_type": row[3],
            "is_enabled": row[4],
            "notification_time": row[5],
            "timezone": row[6]
        })

    return settings


async def toggle_notification(user_id: int, notification_type: str, enabled: bool) -> bool:
    """Toggle notification on/off for a user."""
    db = get_db()

    query = """
        UPDATE notification_settings
        SET is_enabled = ?
        WHERE user_id = ? AND notification_type = ?
    """

    await db.execute(query, (enabled, user_id, notification_type))
    return True


# ============================================================================
# ACTIVITY LOG
# ============================================================================

async def log_activity(user_id: Optional[int], action: str, details: Optional[str] = None):
    """Log user activity."""
    db = get_db()

    query = """
        INSERT INTO activity_log (user_id, action, details)
        VALUES (?, ?, ?)
    """

    await db.execute(query, (user_id, action, details))


# ============================================================================
# GRADES CACHE (кеш оценок для уведомлений)
# ============================================================================

async def get_cached_grade_keys(child_id: int) -> set:
    """Получить множество ключей уже закешированных оценок."""
    db = get_db()
    rows = await db.fetchall(
        "SELECT subject, grade_value, date, lesson_type FROM grades_cache WHERE child_id = ?",
        (child_id,),
    )
    return {(row[0], row[1], str(row[2]), row[3] or "") for row in rows}


async def cache_new_grades(child_id: int, grades: List[Dict]) -> int:
    """
    Сохранить новые оценки в кеш. Возвращает количество новых.

    grades: список dict с ключами subject, grade_value, date, lesson_type, teacher, comment.
    """
    existing = await get_cached_grade_keys(child_id)
    db = get_db()
    new_count = 0

    for g in grades:
        key = (g["subject"], g["grade_value"], str(g["date"]), g.get("lesson_type") or "")
        if key not in existing:
            await db.execute(
                """INSERT INTO grades_cache (child_id, subject, grade_value, date, lesson_type, teacher, comment)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (child_id, g["subject"], g["grade_value"], str(g["date"]),
                 g.get("lesson_type"), g.get("teacher"), g.get("comment")),
            )
            new_count += 1

    return new_count


async def get_unnotified_grades(child_id: int) -> List[Dict]:
    """Получить оценки, о которых ещё не отправлено уведомление."""
    db = get_db()
    rows = await db.fetchall(
        """SELECT grade_id, subject, grade_value, date, lesson_type, comment
           FROM grades_cache WHERE child_id = ? AND is_notified = 0""",
        (child_id,),
    )
    return [
        {"grade_id": row[0], "subject": row[1], "grade_value": row[2],
         "date": row[3], "lesson_type": row[4], "comment": row[5]}
        for row in rows
    ]


async def mark_grades_notified(grade_ids: List[int]) -> None:
    """Пометить оценки как отправленные."""
    if not grade_ids:
        return
    db = get_db()
    placeholders = ",".join("?" * len(grade_ids))
    await db.execute(
        f"UPDATE grades_cache SET is_notified = 1 WHERE grade_id IN ({placeholders})",
        tuple(grade_ids),
    )


# ============================================================================
# HOMEWORK CACHE (кеш ДЗ для уведомлений)
# ============================================================================

async def get_cached_homework_keys(child_id: int) -> set:
    """Получить множество ключей уже закешированных ДЗ."""
    db = get_db()
    rows = await db.fetchall(
        "SELECT subject, assignment, due_date FROM homework_cache WHERE child_id = ?",
        (child_id,),
    )
    return {(row[0], (row[1] or "")[:100], str(row[2])) for row in rows}


async def cache_new_homework(child_id: int, homework_list: List[Dict]) -> int:
    """Сохранить новые ДЗ в кеш. Возвращает количество новых."""
    existing = await get_cached_homework_keys(child_id)
    db = get_db()
    new_count = 0

    for hw in homework_list:
        key = (hw["subject"], (hw["assignment"] or "")[:100], str(hw["due_date"]))
        if key not in existing:
            await db.execute(
                """INSERT INTO homework_cache (child_id, subject, assignment, due_date)
                   VALUES (?, ?, ?, ?)""",
                (child_id, hw["subject"], hw["assignment"], str(hw["due_date"])),
            )
            new_count += 1

    return new_count


async def get_unnotified_homework(child_id: int) -> List[Dict]:
    """Получить ДЗ, о которых ещё не отправлено уведомление."""
    db = get_db()
    rows = await db.fetchall(
        """SELECT homework_id, subject, assignment, due_date
           FROM homework_cache WHERE child_id = ? AND is_notified = 0""",
        (child_id,),
    )
    return [
        {"homework_id": row[0], "subject": row[1], "assignment": row[2], "due_date": row[3]}
        for row in rows
    ]


async def mark_homework_notified(homework_ids: List[int]) -> None:
    """Пометить ДЗ как отправленные."""
    if not homework_ids:
        return
    db = get_db()
    placeholders = ",".join("?" * len(homework_ids))
    await db.execute(
        f"UPDATE homework_cache SET is_notified = 1 WHERE homework_id IN ({placeholders})",
        tuple(homework_ids),
    )


# ============================================================================
# NOTIFICATION HELPERS (для рассылки)
# ============================================================================

async def get_users_with_notifications(notification_type: str) -> List[Dict]:
    """
    Получить всех пользователей с включёнными уведомлениями данного типа.

    Для grades — только admin/parent. Для homework — все роли.
    Только незаблокированные с МЭШ-токеном.
    """
    db = get_db()

    role_filter = ""
    if notification_type == "grades":
        role_filter = "AND u.role IN ('admin', 'parent')"

    query = f"""
        SELECT ns.user_id, ns.child_id, ns.notification_time, ns.timezone,
               u.mesh_profile_id
        FROM notification_settings ns
        JOIN users u ON ns.user_id = u.user_id
        WHERE ns.notification_type = ?
          AND ns.is_enabled = 1
          AND (u.is_blocked = 0 OR u.is_blocked IS NULL)
          AND u.mesh_token IS NOT NULL
          AND u.mesh_profile_id IS NOT NULL
          {role_filter}
    """
    rows = await db.fetchall(query, (notification_type,))
    return [
        {
            "user_id": row[0],
            "child_id": row[1],
            "notification_time": row[2],
            "timezone": row[3],
            "profile_id": row[4],
        }
        for row in rows
    ]


async def disable_all_notifications(user_id: int) -> None:
    """Отключить все уведомления (бот заблокирован пользователем в Telegram)."""
    db = get_db()
    await db.execute(
        "UPDATE notification_settings SET is_enabled = 0 WHERE user_id = ?",
        (user_id,),
    )


async def cleanup_old_cache(days: int = 30) -> None:
    """Удалить кеш-записи старше N дней."""
    db = get_db()
    await db.execute(
        "DELETE FROM grades_cache WHERE created_at < datetime('now', ?)",
        (f"-{days} days",),
    )
    await db.execute(
        "DELETE FROM homework_cache WHERE created_at < datetime('now', ?)",
        (f"-{days} days",),
    )


# ============================================================================
# ACCESS CONTROL (роли и доступ)
# ============================================================================

async def is_user_allowed(user_id: int) -> tuple:
    """Check if user is in whitelist and not blocked.

    Returns:
        (is_allowed: bool, role: str | None)
    """
    db = get_db()
    row = await db.fetchone(
        "SELECT role, is_blocked FROM users WHERE user_id = ?",
        (user_id,),
    )
    if row is None:
        return (False, None)
    if row[1]:  # is_blocked
        return (False, row[0])
    return (True, row[0])


async def get_user_role(user_id: int) -> Optional[str]:
    """Get user role (admin/parent/student) or None if not found."""
    db = get_db()
    row = await db.fetchone(
        "SELECT role FROM users WHERE user_id = ? AND is_blocked = 0",
        (user_id,),
    )
    return row[0] if row else None


async def set_user_access(user_id: int, role: str = "student") -> None:
    """Add or update a user with given role. Also unblocks if was blocked."""
    db = get_db()
    # Проверяем, существует ли пользователь
    existing = await db.fetchone("SELECT 1 FROM users WHERE user_id = ?", (user_id,))
    if existing:
        await db.execute(
            "UPDATE users SET role = ?, is_blocked = 0 WHERE user_id = ?",
            (role, user_id),
        )
    else:
        await db.execute(
            "INSERT INTO users (user_id, role, is_blocked) VALUES (?, ?, 0)",
            (user_id, role),
        )


async def block_user(user_id: int) -> bool:
    """Block a user. Returns True if user existed, False otherwise."""
    db = get_db()
    conn = await db.connect()
    cursor = await conn.execute(
        "UPDATE users SET is_blocked = 1 WHERE user_id = ?",
        (user_id,),
    )
    await conn.commit()
    return cursor.rowcount > 0


async def get_all_users_list() -> List[Dict]:
    """Get all users with their roles and block status."""
    db = get_db()
    rows = await db.fetchall(
        "SELECT user_id, first_name, username, role, is_blocked FROM users ORDER BY user_id"
    )
    return [
        {
            "user_id": row[0],
            "first_name": row[1],
            "username": row[2],
            "role": row[3],
            "is_blocked": row[4],
        }
        for row in rows
    ]


async def ensure_quiz_user(
    user_id: int,
    username: Optional[str] = None,
    first_name: Optional[str] = None,
) -> None:
    """Create or update a quiz user record (обновить last_active)."""
    db = get_db()
    existing = await db.fetchone("SELECT 1 FROM users WHERE user_id = ?", (user_id,))
    if existing:
        await db.execute(
            "UPDATE users SET username = ?, first_name = ?, last_active = datetime('now') WHERE user_id = ?",
            (username, first_name, user_id),
        )
    else:
        await db.execute(
            "INSERT INTO users (user_id, username, first_name, role) VALUES (?, ?, ?, 'student')",
            (user_id, username, first_name),
        )


# ============================================================================
# QUIZ / TEST SESSIONS
# ============================================================================

async def save_test_session(
    user_id: int,
    language: str,
    topic: str,
    total: int,
    correct: int,
    percent: float,
    answers: List[Dict],
) -> int:
    """Save a completed test session and its individual question results."""
    db = get_db()
    conn = await db.connect()

    cursor = await conn.execute(
        """INSERT INTO test_sessions (user_id, language, topic, total_questions, correct_answers, score_percent)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (user_id, language, topic, total, correct, percent),
    )
    session_id = cursor.lastrowid

    for a in answers:
        await conn.execute(
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

    await conn.commit()
    return session_id


async def get_user_sessions(user_id: int, limit: int = 10) -> List[Dict]:
    """Get recent test sessions for a user."""
    db = get_db()
    rows = await db.fetchall(
        """SELECT id, language, topic, total_questions, correct_answers, score_percent, finished_at
           FROM test_sessions
           WHERE user_id = ?
           ORDER BY finished_at DESC
           LIMIT ?""",
        (user_id, limit),
    )
    return [
        {
            "id": row[0],
            "language": row[1],
            "topic": row[2],
            "total_questions": row[3],
            "correct_answers": row[4],
            "score_percent": row[5],
            "finished_at": row[6],
        }
        for row in rows
    ]


async def get_weak_topics(user_id: int) -> List[Dict]:
    """Get topics where the user scored below 70%."""
    db = get_db()
    rows = await db.fetchall(
        """SELECT language, topic, AVG(score_percent) as avg_score, COUNT(*) as attempts
           FROM test_sessions
           WHERE user_id = ?
           GROUP BY language, topic
           HAVING avg_score < 70
           ORDER BY avg_score ASC""",
        (user_id,),
    )
    return [
        {
            "language": row[0],
            "topic": row[1],
            "avg_score": row[2],
            "attempts": row[3],
        }
        for row in rows
    ]


async def get_recent_questions(
    user_id: int, language: str, topic: str, limit: int = 50,
) -> List[str]:
    """Get recent question texts for deduplication."""
    db = get_db()
    rows = await db.fetchall(
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
    return [row[0] for row in rows]


async def get_stats_summary(user_id: int) -> Dict:
    """Get overall stats for a user."""
    db = get_db()
    row = await db.fetchone(
        """SELECT
               COUNT(*) as total_tests,
               AVG(score_percent) as avg_score,
               SUM(total_questions) as total_questions_answered,
               SUM(correct_answers) as total_correct
           FROM test_sessions
           WHERE user_id = ?""",
        (user_id,),
    )
    if not row:
        return {}
    return {
        "total_tests": row[0],
        "avg_score": row[1],
        "total_questions_answered": row[2],
        "total_correct": row[3],
    }
