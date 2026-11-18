"""Asynchronous database operations used by handlers and services."""

import math
import time

from db.database import adapt_sql, fetch_all, fetch_one, is_postgres, open_database
from models import Contact, Rule


async def register_user(telegram_id: int, name: str) -> None:
    """Insert a user, or refresh their display name without duplicating them."""
    async with open_database() as connection:
        cursor = await connection.execute(
            adapt_sql("""
            INSERT INTO users (telegram_id, name) VALUES (?, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET name = excluded.name
            """),
            (telegram_id, name),
        )
        await connection.commit()
        await cursor.close()


async def get_user_name(telegram_id: int) -> str | None:
    """Return the user's display name, if registered."""
    async with open_database() as connection:
        row = await fetch_one(
            connection,
            "SELECT name FROM users WHERE telegram_id = ?",
            (telegram_id,),
        )
    return str(row["name"]) if row else None


async def add_contact(
    owner_id: int, contact_telegram_id: int, contact_name: str
) -> None:
    """Add or refresh a contact relation between two registered users."""
    async with open_database() as connection:
        cursor = await connection.execute(
            adapt_sql("""
            INSERT INTO contacts (owner_id, contact_telegram_id, contact_name)
            VALUES (?, ?, ?)
            ON CONFLICT(owner_id, contact_telegram_id)
            DO UPDATE SET contact_name = excluded.contact_name
            """),
            (owner_id, contact_telegram_id, contact_name),
        )
        await connection.commit()
        await cursor.close()


async def get_contacts(owner_id: int) -> list[Contact]:
    """Return all contacts registered for an owner."""
    async with open_database() as connection:
        rows = await fetch_all(
            connection,
            """
            SELECT id, owner_id, contact_telegram_id, contact_name
            FROM contacts WHERE owner_id = ? ORDER BY contact_name
            """,
            (owner_id,),
        )
    return [
        Contact(
            id=int(row["id"]),
            owner_id=int(row["owner_id"]),
            contact_telegram_id=int(row["contact_telegram_id"]),
            contact_name=str(row["contact_name"]),
        )
        for row in rows
    ]


async def create_rule(
    owner_id: int,
    contact_id: int,
    lat: float,
    lon: float,
    radius_m: int,
    text: str,
) -> int:
    """Persist a location rule and return its database ID."""
    if not all(math.isfinite(value) for value in (lat, lon)):
        raise ValueError("Coordinates must be finite numbers")
    if not -90 <= lat <= 90:
        raise ValueError("Latitude must be between -90 and 90 degrees")
    if not -180 <= lon <= 180:
        raise ValueError("Longitude must be between -180 and 180 degrees")
    if not 1 <= radius_m <= 100_000:
        raise ValueError("Radius must be between 1 and 100000 meters")
    if not text.strip() or len(text) > 500:
        raise ValueError("Message text must contain 1 to 500 characters")

    async with open_database() as connection:
        query = """
            INSERT INTO rules
                (owner_id, contact_id, latitude, longitude, radius_m, message_text)
            SELECT ?, contacts.id, ?, ?, ?, ?
            FROM contacts
            WHERE contacts.id = ? AND contacts.owner_id = ?
        """
        if is_postgres():
            cursor = await connection.execute(
                adapt_sql(query + " RETURNING id"),
                (owner_id, lat, lon, radius_m, text, contact_id, owner_id),
            )
            row = await cursor.fetchone()
            rule_id = int(row["id"]) if row else None
            await cursor.close()
        else:
            cursor = await connection.execute(
                query, (owner_id, lat, lon, radius_m, text, contact_id, owner_id)
            )
            rule_id = int(cursor.lastrowid) if cursor.rowcount == 1 else None
        if rule_id is None:
            raise ValueError("The selected contact does not belong to this user")
        await connection.commit()
        return rule_id


async def get_active_rules(owner_id: int) -> list[Rule]:
    """Return active rules with the recipient Telegram ID."""
    async with open_database() as connection:
        rows = await fetch_all(
            connection,
            """
            SELECT r.id, r.owner_id, r.contact_id, r.latitude, r.longitude,
                   r.radius_m, r.message_text, r.is_inside,
                   c.contact_telegram_id
            FROM rules AS r
            JOIN contacts AS c ON c.id = r.contact_id
            WHERE r.owner_id = ? AND r.is_active = 1
            """,
            (owner_id,),
        )
    return [
        Rule(
            id=int(row["id"]),
            owner_id=int(row["owner_id"]),
            contact_id=int(row["contact_id"]),
            latitude=float(row["latitude"]),
            longitude=float(row["longitude"]),
            radius_m=int(row["radius_m"]),
            message_text=str(row["message_text"]),
            is_inside=bool(row["is_inside"]),
            contact_telegram_id=int(row["contact_telegram_id"]),
        )
        for row in rows
    ]


async def update_rule_inside_if_changed(
    rule_id: int, owner_id: int, expected_inside: bool, new_inside: bool
) -> bool:
    """Atomically update an owned rule's inside flag only when unchanged."""
    async with open_database() as connection:
        cursor = await connection.execute(
            adapt_sql("""
            UPDATE rules SET is_inside = ?
            WHERE id = ? AND owner_id = ? AND is_active = 1 AND is_inside = ?
            """),
            (int(new_inside), rule_id, owner_id, int(expected_inside)),
        )
        await connection.commit()
        changed = cursor.rowcount == 1
        await cursor.close()
        return changed


async def consume_rate_limit(
    telegram_id: int, action: str, limit: int, window_seconds: int
) -> bool:
    """Atomically consume one per-user allowance in the current time window."""
    if limit <= 0 or window_seconds <= 0:
        raise ValueError("Rate-limit values must be positive")
    window_start = int(time.time()) // window_seconds
    async with open_database() as connection:
        cursor = await connection.execute(
            adapt_sql("""
            INSERT INTO rate_limits
                (telegram_id, action, window_start, request_count)
            VALUES (?, ?, ?, 1)
            ON CONFLICT(telegram_id, action) DO UPDATE SET
                request_count = CASE
                    WHEN rate_limits.window_start = excluded.window_start
                    THEN rate_limits.request_count + 1
                    ELSE 1
                END,
                window_start = excluded.window_start
            """),
            (telegram_id, action, window_start),
        )
        row = await fetch_one(
            connection,
            """
            SELECT request_count FROM rate_limits
            WHERE telegram_id = ? AND action = ?
            """,
            (telegram_id, action),
        )
        await connection.commit()
        await cursor.close()
    return row is not None and int(row["request_count"]) <= limit
