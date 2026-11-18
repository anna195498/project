"""Asynchronous database operations used by handlers and services."""

from db.database import open_database
from models import Contact, Rule


async def register_user(telegram_id: int, name: str) -> None:
    """Insert a user, or refresh their display name without duplicating them."""
    async with open_database() as connection:
        await connection.execute(
            """
            INSERT INTO users (telegram_id, name) VALUES (?, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET name = excluded.name
            """,
            (telegram_id, name),
        )
        await connection.commit()


async def get_user_name(telegram_id: int) -> str | None:
    """Return the user's display name, if registered."""
    async with open_database() as connection:
        async with connection.execute(
            "SELECT name FROM users WHERE telegram_id = ?", (telegram_id,)
        ) as cursor:
            row = await cursor.fetchone()
    return str(row["name"]) if row else None


async def add_contact(
    owner_id: int, contact_telegram_id: int, contact_name: str
) -> None:
    """Add or refresh a contact relation between two registered users."""
    async with open_database() as connection:
        await connection.execute(
            """
            INSERT INTO contacts (owner_id, contact_telegram_id, contact_name)
            VALUES (?, ?, ?)
            ON CONFLICT(owner_id, contact_telegram_id)
            DO UPDATE SET contact_name = excluded.contact_name
            """,
            (owner_id, contact_telegram_id, contact_name),
        )
        await connection.commit()


async def get_contacts(owner_id: int) -> list[Contact]:
    """Return all contacts registered for an owner."""
    async with open_database() as connection:
        async with connection.execute(
            """
            SELECT id, owner_id, contact_telegram_id, contact_name
            FROM contacts WHERE owner_id = ? ORDER BY contact_name
            """,
            (owner_id,),
        ) as cursor:
            rows = await cursor.fetchall()
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
    async with open_database() as connection:
        cursor = await connection.execute(
            """
            INSERT INTO rules
                (owner_id, contact_id, latitude, longitude, radius_m, message_text)
            SELECT ?, contacts.id, ?, ?, ?, ?
            FROM contacts
            WHERE contacts.id = ? AND contacts.owner_id = ?
            """,
            (owner_id, lat, lon, radius_m, text, contact_id, owner_id),
        )
        if cursor.rowcount != 1 or cursor.lastrowid is None:
            raise ValueError("The selected contact does not belong to this user")
        await connection.commit()
        return int(cursor.lastrowid)


async def get_active_rules(owner_id: int) -> list[Rule]:
    """Return active rules with the recipient Telegram ID."""
    async with open_database() as connection:
        async with connection.execute(
            """
            SELECT r.id, r.owner_id, r.contact_id, r.latitude, r.longitude,
                   r.radius_m, r.message_text, r.is_inside,
                   c.contact_telegram_id
            FROM rules AS r
            JOIN contacts AS c ON c.id = r.contact_id
            WHERE r.owner_id = ? AND r.is_active = 1
            """,
            (owner_id,),
        ) as cursor:
            rows = await cursor.fetchall()
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
    rule_id: int, expected_inside: bool, new_inside: bool
) -> bool:
    """Atomically update a rule's inside flag only when it has not changed."""
    async with open_database() as connection:
        cursor = await connection.execute(
            """
            UPDATE rules SET is_inside = ?
            WHERE id = ? AND is_active = 1 AND is_inside = ?
            """,
            (int(new_inside), rule_id, int(expected_inside)),
        )
        await connection.commit()
        return cursor.rowcount == 1
