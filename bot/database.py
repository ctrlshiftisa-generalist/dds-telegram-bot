"""SQLite database operations for users and request history."""

import aiosqlite
from pathlib import Path
from datetime import datetime
from typing import Optional

_db_path: str = ""


async def init_db(db_path: str) -> None:
    """Initialize database and create tables."""
    global _db_path
    _db_path = db_path
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    async with aiosqlite.connect(db_path) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                telegram_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER NOT NULL,
                employee_name TEXT NOT NULL,
                date TEXT NOT NULL,
                operation_type TEXT NOT NULL,
                amount REAL NOT NULL,
                project TEXT NOT NULL,
                period TEXT NOT NULL,
                comment TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'sent',
                created_at TEXT NOT NULL,
                FOREIGN KEY (telegram_id) REFERENCES users(telegram_id)
            )
        """)
        await db.commit()


def _get_path() -> str:
    if not _db_path:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _db_path


async def get_user(telegram_id: int) -> Optional[dict]:
    """Get user by telegram_id."""
    async with aiosqlite.connect(_get_path()) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
        )
        row = await cursor.fetchone()
        if row:
            return dict(row)
        return None


async def create_user(telegram_id: int, name: str) -> None:
    """Register a new user."""
    async with aiosqlite.connect(_get_path()) as db:
        await db.execute(
            "INSERT OR REPLACE INTO users (telegram_id, name, created_at) VALUES (?, ?, ?)",
            (telegram_id, name, datetime.now().isoformat()),
        )
        await db.commit()


async def save_request(
    telegram_id: int,
    employee_name: str,
    date: str,
    operation_type: str,
    amount: float,
    project: str,
    period: str,
    comment: str,
    status: str = "sent",
) -> int:
    """Save a request record to the database. Returns the request ID."""
    async with aiosqlite.connect(_get_path()) as db:
        cursor = await db.execute(
            """INSERT INTO requests 
            (telegram_id, employee_name, date, operation_type, amount, project, period, comment, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                telegram_id,
                employee_name,
                date,
                operation_type,
                amount,
                project,
                period,
                comment,
                status,
                datetime.now().isoformat(),
            ),
        )
        await db.commit()
        return cursor.lastrowid


async def get_user_request_count(telegram_id: int) -> int:
    """Count requests made by user."""
    async with aiosqlite.connect(_get_path()) as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM requests WHERE telegram_id = ?", (telegram_id,)
        )
        row = await cursor.fetchone()
        return row[0] if row else 0
