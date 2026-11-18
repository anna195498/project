"""PostgreSQL-backed aiogram FSM storage for serverless deployments."""

import json
from collections.abc import Mapping
from typing import Any

from aiogram.fsm.storage.base import BaseStorage, StorageKey, StateType

from db.database import adapt_sql, fetch_one, is_postgres, open_database


class PostgresStorage(BaseStorage):
    """Persist FSM state and data across Vercel function invocations."""

    def _storage_key(self, key: StorageKey) -> str:
        """Serialize all aiogram key fields into a stable database key."""
        return json.dumps(
            [
                key.bot_id,
                key.chat_id,
                key.user_id,
                key.thread_id,
                key.business_connection_id,
                key.destiny,
                key.is_guest,
            ],
            separators=(",", ":"),
        )

    async def set_state(self, key: StorageKey, state: StateType = None) -> None:
        """Store or clear a user's current FSM state."""
        state_value = state.state if hasattr(state, "state") else state
        async with open_database() as connection:
            cursor = await connection.execute(
                adapt_sql("""
                INSERT INTO fsm_storage (storage_key, state)
                VALUES (?, ?)
                ON CONFLICT(storage_key)
                DO UPDATE SET state = excluded.state
                """),
                (self._storage_key(key), state_value),
            )
            await connection.commit()
            await cursor.close()

    async def get_state(self, key: StorageKey) -> str | None:
        """Read the persisted state for a user."""
        async with open_database() as connection:
            row = await fetch_one(
                connection,
                "SELECT state FROM fsm_storage WHERE storage_key = ?",
                (self._storage_key(key),),
            )
        return str(row["state"]) if row and row["state"] is not None else None

    async def set_data(self, key: StorageKey, data: Mapping[str, Any]) -> None:
        """Replace the persisted data for a user's FSM."""
        serialized = json.dumps(dict(data), separators=(",", ":"))
        query = """
            INSERT INTO fsm_storage (storage_key, data)
            VALUES (?, ?)
            ON CONFLICT(storage_key)
            DO UPDATE SET data = excluded.data
        """
        if is_postgres():
            query = """
                INSERT INTO fsm_storage (storage_key, data)
                VALUES (?, ?::jsonb)
                ON CONFLICT(storage_key)
                DO UPDATE SET data = excluded.data
            """
        async with open_database() as connection:
            cursor = await connection.execute(
                adapt_sql(query),
                (self._storage_key(key), serialized),
            )
            await connection.commit()
            await cursor.close()

    async def get_data(self, key: StorageKey) -> dict[str, Any]:
        """Read persisted FSM data, returning an empty mapping for new users."""
        async with open_database() as connection:
            row = await fetch_one(
                connection,
                "SELECT data FROM fsm_storage WHERE storage_key = ?",
                (self._storage_key(key),),
            )
        if row is None:
            return {}
        data = row["data"]
        if isinstance(data, str):
            data = json.loads(data)
        return dict(data)

    async def close(self) -> None:
        """Leave the shared database pool open for other function requests."""
        return None
