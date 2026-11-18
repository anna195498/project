"""SQLite connection and schema management."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite

from config import get_settings


async def initialize_database(database_path: str | None = None) -> None:
    """Create the database schema if it does not exist."""
    path = database_path or get_settings().database_path
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(path) as connection:
        await connection.execute("PRAGMA foreign_keys = ON")
        await connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                telegram_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS contacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id INTEGER NOT NULL REFERENCES users(telegram_id)
                    ON DELETE CASCADE,
                contact_telegram_id INTEGER NOT NULL REFERENCES users(telegram_id)
                    ON DELETE CASCADE,
                contact_name TEXT NOT NULL,
                UNIQUE(owner_id, contact_telegram_id),
                CHECK(owner_id != contact_telegram_id)
            );

            CREATE TABLE IF NOT EXISTS rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id INTEGER NOT NULL REFERENCES users(telegram_id)
                    ON DELETE CASCADE,
                contact_id INTEGER NOT NULL REFERENCES contacts(id)
                    ON DELETE CASCADE,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                radius_m INTEGER NOT NULL DEFAULT 100 CHECK(radius_m > 0),
                message_text TEXT NOT NULL,
                is_inside INTEGER NOT NULL DEFAULT 0 CHECK(is_inside IN (0, 1)),
                is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0, 1))
            );
            """
        )
        await connection.commit()


def get_database_path() -> str:
    """Return the configured SQLite database path."""
    return get_settings().database_path


@asynccontextmanager
async def open_database() -> AsyncIterator[aiosqlite.Connection]:
    """Open a connection with foreign-key enforcement enabled."""
    connection = await aiosqlite.connect(get_database_path())
    connection.row_factory = aiosqlite.Row
    await connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
    finally:
        await connection.close()
