"""Database initialization and connection management."""
import logging
import aiosqlite
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class Database:
    """Database connection manager."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._conn: Optional[aiosqlite.Connection] = None

    async def connect(self) -> aiosqlite.Connection:
        """Establish database connection."""
        if self._conn is None:
            # Ensure data directory exists
            db_dir = Path(self.db_path).parent
            db_dir.mkdir(parents=True, exist_ok=True)

            self._conn = await aiosqlite.connect(self.db_path)
            # Enable foreign keys
            await self._conn.execute("PRAGMA foreign_keys = ON")
            # Row factory для доступа к колонкам по имени (поддерживает и row[0], и row["name"])
            self._conn.row_factory = aiosqlite.Row
            await self._conn.commit()

        return self._conn

    async def close(self):
        """Close database connection."""
        if self._conn:
            await self._conn.close()
            self._conn = None

    async def execute(self, query: str, params: tuple = ()):
        """Execute a query."""
        conn = await self.connect()
        await conn.execute(query, params)
        await conn.commit()

    async def fetchone(self, query: str, params: tuple = ()):
        """Fetch one result."""
        conn = await self.connect()
        async with conn.execute(query, params) as cursor:
            return await cursor.fetchone()

    async def fetchall(self, query: str, params: tuple = ()):
        """Fetch all results."""
        conn = await self.connect()
        async with conn.execute(query, params) as cursor:
            return await cursor.fetchall()


async def init_database(db_path: str = "data/school_bot.db"):
    """Initialize database with schema from migrations/init.sql."""
    # Read SQL schema
    migrations_path = Path(__file__).parent.parent / "database" / "migrations" / "init.sql"

    if not migrations_path.exists():
        raise FileNotFoundError(f"Migration file not found: {migrations_path}")

    with open(migrations_path, "r", encoding="utf-8") as f:
        schema_sql = f.read()

    # Create database and execute schema
    db = Database(db_path)
    conn = await db.connect()

    # Execute schema (split by ; and execute each statement)
    statements = schema_sql.split(";")
    for statement in statements:
        statement = statement.strip()
        if statement:
            await conn.execute(statement)

    await conn.commit()

    # Запуск дополнительных миграций для существующих БД
    await _run_migrations(conn)

    print(f"Database initialized successfully at {db_path}")

    return db


async def _run_migrations(conn: aiosqlite.Connection):
    """Применяет миграции для существующих БД (ALTER TABLE и т.п.)."""
    migrations_dir = Path(__file__).parent.parent / "database" / "migrations"

    # Проверяем, есть ли уже новые колонки (идемпотентность)
    cursor = await conn.execute("PRAGMA table_info(users)")
    user_columns = {row[1] for row in await cursor.fetchall()}

    if "mesh_refresh_token" not in user_columns:
        migration_file = migrations_dir / "002_add_mesh_oauth_fields.sql"
        if migration_file.exists():
            with open(migration_file, "r", encoding="utf-8") as f:
                sql = f.read()
            for statement in sql.split(";"):
                statement = statement.strip()
                if statement:
                    try:
                        await conn.execute(statement)
                    except Exception as e:
                        logger.debug("Migration 002 statement skipped: %s", e)
            await conn.commit()

    # Миграция 003: тестирование по языкам + контроль доступа
    if "role" not in user_columns:
        migration_file = migrations_dir / "003_add_quiz_and_access.sql"
        if migration_file.exists():
            with open(migration_file, "r", encoding="utf-8") as f:
                sql = f.read()
            for statement in sql.split(";"):
                statement = statement.strip()
                if statement:
                    try:
                        await conn.execute(statement)
                    except Exception as e:
                        logger.debug("Migration 003 statement skipped: %s", e)
            await conn.commit()

    # Миграция 004: таблица notification_runs (отслеживание пропущенных уведомлений)
    try:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS notification_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                notification_type TEXT NOT NULL,
                run_date DATE NOT NULL,
                completed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(notification_type, run_date)
            )
        """)
        await conn.commit()
    except Exception as e:
        logger.debug("Migration 004 (notification_runs) skipped: %s", e)

    # Авто-создание главного админа (ADMIN_ID из .env)
    await _ensure_admin(conn)


async def _ensure_admin(conn: aiosqlite.Connection):
    """Создаёт/обновляет главного админа из ADMIN_ID."""
    try:
        from config import settings
        admin_id = settings.ADMIN_ID
        if not admin_id:
            return
        # Проверяем, есть ли уже такой пользователь
        cursor = await conn.execute("SELECT 1 FROM users WHERE user_id = ?", (admin_id,))
        exists = await cursor.fetchone()
        if exists:
            await conn.execute(
                "UPDATE users SET role = 'admin', is_blocked = 0 WHERE user_id = ?",
                (admin_id,),
            )
        else:
            await conn.execute(
                "INSERT INTO users (user_id, role, is_blocked, mesh_login, mesh_password) VALUES (?, 'admin', 0, '', '')",
                (admin_id,),
            )
        await conn.commit()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("_ensure_admin не удалось: %s", e)


# Global database instance (will be initialized in bot.py)
db: Optional[Database] = None


def get_db() -> Database:
    """Get global database instance."""
    if db is None:
        raise RuntimeError("Database not initialized. Call init_database() first.")
    return db
