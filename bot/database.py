"""SQLite database operations for users, admins, operation types, projects and request history."""

import aiosqlite
from pathlib import Path
from datetime import datetime
from typing import Optional

_db_path: str = ""

# ── Seed data: initial operation types ──────────────────────────────────────
_INITIAL_OPERATION_TYPES = [
    # (name, auto_project, needs_project, project_list_range, requisites_hint)
    (
        "Съёмки",
        None,
        1,
        "Списки!L2:L",
        "Введите реквизиты карты (16 цифр):",
    ),
    (
        "Пиар",
        None,
        1,
        "Списки!M2:M",
        "Введите реквизиты и назначение платежа\n(например: <code>0000 0000 0000 0000 блогер Нури</code>):",
    ),
    (
        "Подписки",
        "A.M. Maison",
        0,
        None,
        "Введите реквизиты и назначение платежа\n(например: <code>0000 0000 0000 0000 GPT</code>):",
    ),
    (
        "Другое",
        "A.M. Maison",
        0,
        None,
        "Введите реквизиты и назначение платежа\n(например: <code>0000 0000 0000 0000 вода в офис</code>):",
    ),
]


async def init_db(db_path: str) -> None:
    """Initialize database and create tables."""
    global _db_path
    _db_path = db_path
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    async with aiosqlite.connect(db_path) as db:
        # ── Users ──────────────────────────────────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                telegram_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                position TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                is_banned INTEGER NOT NULL DEFAULT 0
            )
        """)

        # Add is_banned column if it doesn't exist (migration)
        # Migrations for existing databases
        for col_sql in [
            "ALTER TABLE users ADD COLUMN is_banned INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE users ADD COLUMN position TEXT NOT NULL DEFAULT ''",
        ]:
            try:
                await db.execute(col_sql)
            except aiosqlite.OperationalError:
                pass  # Column likely already exists

        # ── Admins (appointed by developer) ───────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                telegram_id INTEGER PRIMARY KEY,
                added_by    INTEGER NOT NULL,
                added_at    TEXT NOT NULL
            )
        """)

        # ── Operation types (entities) — dynamically extensible ───────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS operation_types (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                name                TEXT NOT NULL UNIQUE,
                auto_project        TEXT,
                needs_project       INTEGER NOT NULL DEFAULT 1,
                project_list_range  TEXT,
                requisites_hint     TEXT NOT NULL DEFAULT 'Введите реквизиты:',
                sort_order          INTEGER NOT NULL DEFAULT 100,
                created_at          TEXT NOT NULL
            )
        """)

        # ── Requests history ───────────────────────────────────────────────
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

        # ── Seed operation types if empty ──────────────────────────────────
        cursor = await db.execute("SELECT COUNT(*) FROM operation_types")
        count = (await cursor.fetchone())[0]
        if count == 0:
            for i, (name, auto_proj, needs_proj, range_, hint) in enumerate(_INITIAL_OPERATION_TYPES):
                await db.execute(
                    """INSERT INTO operation_types
                       (name, auto_project, needs_project, project_list_range, requisites_hint, sort_order, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (name, auto_proj, needs_proj, range_, hint, i * 10, datetime.now().isoformat()),
                )
            await db.commit()


def _get_path() -> str:
    if not _db_path:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _db_path


# ── Users ──────────────────────────────────────────────────────────────────

async def get_user(telegram_id: int) -> Optional[dict]:
    """Get user by telegram_id."""
    async with aiosqlite.connect(_get_path()) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_all_users() -> list[dict]:
    """Get all registered users."""
    async with aiosqlite.connect(_get_path()) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM users ORDER BY name")
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def set_user_ban_status(telegram_id: int, is_banned: bool) -> None:
    """Toggle user ban status."""
    async with aiosqlite.connect(_get_path()) as db:
        await db.execute(
            "UPDATE users SET is_banned = ? WHERE telegram_id = ?",
            (1 if is_banned else 0, telegram_id)
        )
        await db.commit()


async def create_user(telegram_id: int, name: str, position: str = "") -> None:
    """Register a new user. Preserves ban status on re-registration."""
    async with aiosqlite.connect(_get_path()) as db:
        # Check if exists first to preserve ban status
        cursor = await db.execute("SELECT is_banned FROM users WHERE telegram_id = ?", (telegram_id,))
        row = await cursor.fetchone()
        is_banned = row[0] if row else 0
        
        await db.execute(
            "INSERT OR REPLACE INTO users (telegram_id, name, position, created_at, is_banned) VALUES (?, ?, ?, ?, ?)",
            (telegram_id, name, position, datetime.now().isoformat(), is_banned),
        )
        await db.commit()


# ── Admins ─────────────────────────────────────────────────────────────────

async def add_admin(telegram_id: int, added_by: int) -> bool:
    """Add a new admin. Returns False if already exists."""
    async with aiosqlite.connect(_get_path()) as db:
        try:
            await db.execute(
                "INSERT INTO admins (telegram_id, added_by, added_at) VALUES (?, ?, ?)",
                (telegram_id, added_by, datetime.now().isoformat()),
            )
            await db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False


async def remove_admin(telegram_id: int) -> bool:
    """Remove an admin. Returns False if not found."""
    async with aiosqlite.connect(_get_path()) as db:
        cursor = await db.execute(
            "DELETE FROM admins WHERE telegram_id = ?", (telegram_id,)
        )
        await db.commit()
        return cursor.rowcount > 0


async def is_admin(telegram_id: int, developer_ids: list[int], owner_id: int = None) -> bool:
    """Check if a user has admin privileges (developer, owner, or appointed admin)."""
    if telegram_id in developer_ids or (owner_id and telegram_id == owner_id):
        return True
    async with aiosqlite.connect(_get_path()) as db:
        cursor = await db.execute(
            "SELECT 1 FROM admins WHERE telegram_id = ?", (telegram_id,)
        )
        return await cursor.fetchone() is not None


async def get_all_admins() -> list[dict]:
    """Get list of all admins."""
    async with aiosqlite.connect(_get_path()) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT telegram_id, added_by, added_at FROM admins ORDER BY added_at"
        )
        return [dict(row) for row in await cursor.fetchall()]


# ── Operation types ────────────────────────────────────────────────────────

async def get_operation_types() -> list[dict]:
    """Get all operation types ordered by sort_order."""
    async with aiosqlite.connect(_get_path()) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM operation_types ORDER BY sort_order, id"
        )
        return [dict(row) for row in await cursor.fetchall()]


async def get_operation_type(name: str) -> Optional[dict]:
    """Get a single operation type by name."""
    async with aiosqlite.connect(_get_path()) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM operation_types WHERE name = ?", (name,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def add_operation_type(
    name: str,
    auto_project: Optional[str],
    needs_project: bool,
    project_list_range: Optional[str],
    requisites_hint: str,
) -> bool:
    """Add a new operation type (entity). Returns False if already exists."""
    async with aiosqlite.connect(_get_path()) as db:
        try:
            # Sort at the end
            cursor = await db.execute("SELECT MAX(sort_order) FROM operation_types")
            row = await cursor.fetchone()
            max_order = (row[0] or 0) + 10

            await db.execute(
                """INSERT INTO operation_types
                   (name, auto_project, needs_project, project_list_range, requisites_hint, sort_order, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    name,
                    auto_project,
                    1 if needs_project else 0,
                    project_list_range,
                    requisites_hint,
                    max_order,
                    datetime.now().isoformat(),
                ),
            )
            await db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False


# ── Requests ───────────────────────────────────────────────────────────────

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
