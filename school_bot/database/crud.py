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
    Create new user with encrypted credentials.

    Returns:
        True if created successfully
    """
    db = get_db()

    # Encrypt credentials
    encrypted_login = encrypt(mesh_login)
    encrypted_password = encrypt(mesh_password)
    encrypted_token = encrypt(mesh_token) if mesh_token else None
    encrypted_refresh = encrypt(mesh_refresh_token) if mesh_refresh_token else None
    encrypted_client_id = encrypt(mesh_client_id) if mesh_client_id else None
    encrypted_client_secret = encrypt(mesh_client_secret) if mesh_client_secret else None

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
) -> bool:
    """
    Update user's МЭШ session token (and optionally refresh_token).

    Returns:
        True if updated successfully
    """
    db = get_db()

    encrypted_token = encrypt(mesh_token)

    if mesh_refresh_token:
        encrypted_refresh = encrypt(mesh_refresh_token)
        query = """
            UPDATE users
            SET mesh_token = ?, token_expires_at = ?,
                mesh_refresh_token = ?, last_sync = CURRENT_TIMESTAMP
            WHERE user_id = ?
        """
        await db.execute(query, (encrypted_token, token_expires_at, encrypted_refresh, user_id))
    else:
        query = """
            UPDATE users
            SET mesh_token = ?, token_expires_at = ?, last_sync = CURRENT_TIMESTAMP
            WHERE user_id = ?
        """
        await db.execute(query, (encrypted_token, token_expires_at, user_id))

    return True


async def user_exists(user_id: int) -> bool:
    """Check if user exists in database."""
    db = get_db()

    query = "SELECT 1 FROM users WHERE user_id = ?"
    result = await db.fetchone(query, (user_id,))

    return result is not None


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
