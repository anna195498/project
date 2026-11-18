"""SQLite and PostgreSQL connection and schema management."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import aiosqlite

from config import get_settings

_postgres_pool: Any = None


async def initialize_database(database_path: str | None = None) -> None:
    """Create the selected database schema if it does not exist."""
    settings = get_settings()
    if settings.database_url:
        async with open_database() as connection:
            statements = (
                """
                CREATE TABLE IF NOT EXISTS users (
                    telegram_id BIGINT PRIMARY KEY,
                    name TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS contacts (
                    id BIGSERIAL PRIMARY KEY,
                    owner_id BIGINT NOT NULL REFERENCES users(telegram_id)
                        ON DELETE CASCADE,
                    contact_telegram_id BIGINT NOT NULL REFERENCES users(telegram_id)
                        ON DELETE CASCADE,
                    contact_name TEXT NOT NULL,
                    UNIQUE(owner_id, contact_telegram_id),
                    CHECK(owner_id != contact_telegram_id)
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS rules (
                    id BIGSERIAL PRIMARY KEY,
                    owner_id BIGINT NOT NULL REFERENCES users(telegram_id)
                        ON DELETE CASCADE,
                    contact_id BIGINT NOT NULL REFERENCES contacts(id)
                        ON DELETE CASCADE,
                    latitude DOUBLE PRECISION NOT NULL,
                    longitude DOUBLE PRECISION NOT NULL,
                    radius_m INTEGER NOT NULL DEFAULT 100 CHECK(radius_m > 0),
                    message_text TEXT NOT NULL,
                    is_inside SMALLINT NOT NULL DEFAULT 0
                        CHECK(is_inside IN (0, 1)),
                    is_active SMALLINT NOT NULL DEFAULT 1
                        CHECK(is_active IN (0, 1))
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS fsm_storage (
                    storage_key TEXT PRIMARY KEY,
                    state TEXT,
                    data JSONB NOT NULL DEFAULT '{}'::jsonb
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS rate_limits (
                    telegram_id BIGINT NOT NULL,
                    action TEXT NOT NULL,
                    window_start BIGINT NOT NULL,
                    request_count INTEGER NOT NULL,
                    PRIMARY KEY (telegram_id, action)
                )
                """,
            )
            for statement in statements:
                cursor = await connection.execute(statement)
                await cursor.close()
            await connection.commit()
        return

    path = database_path or settings.database_path
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

            CREATE TABLE IF NOT EXISTS fsm_storage (
                storage_key TEXT PRIMARY KEY,
                state TEXT,
                data TEXT NOT NULL DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS rate_limits (
                telegram_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                window_start INTEGER NOT NULL,
                request_count INTEGER NOT NULL,
                PRIMARY KEY (telegram_id, action)
            );
            """
        )
        await connection.commit()


def get_database_path() -> str:
    """Return the configured SQLite database path."""
    return get_settings().database_path


def is_postgres() -> bool:
    """Return whether PostgreSQL is the configured database."""
    return get_settings().database_url is not None


def adapt_sql(query: str) -> str:
    """Convert repository placeholders to the selected driver's format."""
    return query.replace("?", "%s") if is_postgres() else query


async def fetch_one(connection: Any, query: str, parameters: tuple[Any, ...]) -> Any:
    """Fetch one row using the active database driver."""
    cursor = await connection.execute(adapt_sql(query), parameters)
    try:
        return await cursor.fetchone()
    finally:
        await cursor.close()


async def fetch_all(
    connection: Any, query: str, parameters: tuple[Any, ...]
) -> list[Any]:
    """Fetch all rows using the active database driver."""
    cursor = await connection.execute(adapt_sql(query), parameters)
    try:
        return await cursor.fetchall()
    finally:
        await cursor.close()


@asynccontextmanager
async def open_database() -> AsyncIterator[Any]:
    """Open a SQLite connection or a pooled PostgreSQL connection."""
    global _postgres_pool
    settings = get_settings()
    if settings.database_url:
        from psycopg.rows import dict_row
        from psycopg_pool import AsyncConnectionPool

        if _postgres_pool is None:
            _postgres_pool = AsyncConnectionPool(
                conninfo=settings.database_url,
                min_size=0,
                max_size=1,
                kwargs={"row_factory": dict_row, "prepare_threshold": 0},
                open=False,
            )
            await _postgres_pool.open(wait=True)
        async with _postgres_pool.connection() as connection:
            yield connection
        return

    connection = await aiosqlite.connect(settings.database_path)
    connection.row_factory = aiosqlite.Row
    await connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
    finally:
        await connection.close()


async def close_database() -> None:
    """Close the shared PostgreSQL pool when the application shuts down."""
    global _postgres_pool
    if _postgres_pool is not None:
        await _postgres_pool.close()
        _postgres_pool = None
