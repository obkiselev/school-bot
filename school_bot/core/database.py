"""Database initialization and connection management."""
import aiosqlite
import os
from pathlib import Path
from typing import Optional


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
                if statement and not statement.startswith("--"):
                    try:
                        await conn.execute(statement)
                    except Exception:
                        pass  # Колонка уже может существовать
            await conn.commit()


# Global database instance (will be initialized in bot.py)
db: Optional[Database] = None


def get_db() -> Database:
    """Get global database instance."""
    if db is None:
        raise RuntimeError("Database not initialized. Call init_database() first.")
    return db
